// v2 order book: price-indexed ("bitmap") book, multi-instrument,
// crossed-book detection.
//
// Why a new design? The v1 book (book_side.sv) keeps only the N best levels
// in sorted registers; a level that gets pushed out is LOST forever.
// Here every price tick inside a window has its own slot, so NO level is ever
// lost (inside the window), and the number of levels is unlimited.
//
// Per instrument and per side:
//   occ  : W-bit bitmap, bit k = 1  <=>  price (base + k) has quantity
//   qty  : W-entry memory with the quantity of every price tick
//   best : priority encoder over occ (bid = highest set bit, ask = lowest)
//
// Each instrument has its own price window [base, base + W), set through the
// cfg_* port at start of day ("reference data"). Writing a base also clears
// that instrument's book.
//
// Every message is handled in ONE clock cycle (same latency as v1).
// N_INSTR and W must be powers of two.
module price_book #(
    parameter int N_INSTR = 4,
    parameter int W       = 256
) (
    input  logic        clk,
    input  logic        rst,

    // configuration: price window base per instrument
    input  logic        cfg_valid,
    input  logic [15:0] cfg_instrument,
    input  logic [31:0] cfg_base_px,

    // decoded message (from msg_decoder); ignored in a cycle with cfg_valid
    input  logic        msg_valid,
    input  logic        msg_is_bid,
    input  logic [15:0] msg_instrument,
    input  logic [31:0] msg_price,
    input  logic [31:0] msg_qty,

    // top of book of the instrument that just changed
    output logic        tob_valid,       // 1-cycle pulse
    output logic [15:0] tob_instrument,
    output logic [31:0] best_bid_px,     // 0 if that side is empty
    output logic [31:0] best_bid_qty,
    output logic [31:0] best_ask_px,
    output logic [31:0] best_ask_qty,
    output logic        tob_crossed,     // best bid >= best ask

    // rejected messages
    output logic        rej_valid,       // 1-cycle pulse
    output logic [1:0]  rej_reason       // 1 = unknown instrument, 2 = price outside window
);

    localparam int IW = (N_INSTR > 1) ? $clog2(N_INSTR) : 1;
    localparam int AW = $clog2(W);

    localparam logic [1:0] REJ_INSTR = 2'd1;
    localparam logic [1:0] REJ_RANGE = 2'd2;

    // ---------------- storage ----------------
    logic [W-1:0] bid_occ [N_INSTR];
    logic [W-1:0] ask_occ [N_INSTR];
    logic [31:0]  bid_qty [N_INSTR*W];   // address = {instrument, tick}
    logic [31:0]  ask_qty [N_INSTR*W];   // (would be block RAM on an FPGA)
    logic [31:0]  base    [N_INSTR];

    // last top of book we reported, per instrument (to detect changes)
    logic [31:0] t_bpx [N_INSTR], t_bqty [N_INSTR];
    logic [31:0] t_apx [N_INSTR], t_aqty [N_INSTR];

    // ---------------- decode the message ----------------
    logic          instr_ok, in_range, accept;
    logic [IW-1:0] ii;          // instrument slot
    logic [31:0]   base_i, rel;
    logic [AW-1:0] idx;         // price tick inside the window

    assign instr_ok = (msg_instrument < N_INSTR);
    assign ii       = msg_instrument[IW-1:0];
    assign base_i   = base[ii];
    assign rel      = msg_price - base_i;
    assign in_range = (msg_price >= base_i) && (rel < W);
    assign idx      = rel[AW-1:0];
    assign accept   = msg_valid && !cfg_valid && instr_ok && in_range;

    // ---------------- next bitmaps of this instrument ----------------
    logic [W-1:0] bid_row_n, ask_row_n;
    always_comb begin
        bid_row_n = bid_occ[ii];
        ask_row_n = ask_occ[ii];
        if (accept &&  msg_is_bid) bid_row_n[idx] = (msg_qty != 0);
        if (accept && !msg_is_bid) ask_row_n[idx] = (msg_qty != 0);
    end

    // ---------------- priority encoders ----------------
    // bid: HIGHEST occupied tick (later loop iterations win)
    // ask: LOWEST occupied tick  (loop runs downwards)
    logic          bid_any, ask_any;
    logic [AW-1:0] bid_i,   ask_i;
    always_comb begin
        bid_any = 1'b0;  bid_i = '0;
        for (int k = 0; k < W; k++)
            if (bid_row_n[k]) begin bid_any = 1'b1; bid_i = k; end

        ask_any = 1'b0;  ask_i = '0;
        for (int k = W-1; k >= 0; k--)
            if (ask_row_n[k]) begin ask_any = 1'b1; ask_i = k; end
    end

    // ---------------- quantities at the new best ticks ----------------
    // If the best tick is the one being written right now, the memory does
    // not have the new value yet -> forward it from the message ("bypass").
    logic [31:0] bid_q, ask_q;
    always_comb begin
        if (accept && msg_is_bid && bid_i == idx)  bid_q = msg_qty;
        else                                       bid_q = bid_qty[{ii, bid_i}];
        if (accept && !msg_is_bid && ask_i == idx) ask_q = msg_qty;
        else                                       ask_q = ask_qty[{ii, ask_i}];
    end

    // ---------------- new top of book + change / crossed ----------------
    logic [31:0] n_bpx, n_bqty, n_apx, n_aqty;
    logic        changed, crossed_n;
    assign n_bpx  = bid_any ? base_i + bid_i : '0;
    assign n_bqty = bid_any ? bid_q          : '0;
    assign n_apx  = ask_any ? base_i + ask_i : '0;
    assign n_aqty = ask_any ? ask_q          : '0;

    assign changed   = (n_bpx != t_bpx[ii]) || (n_bqty != t_bqty[ii]) ||
                       (n_apx != t_apx[ii]) || (n_aqty != t_aqty[ii]);
    assign crossed_n = bid_any && ask_any && (n_bpx >= n_apx);

    // ---------------- registers ----------------
    logic [IW-1:0] cfg_ii;
    assign cfg_ii = cfg_instrument[IW-1:0];

    always_ff @(posedge clk) begin
        if (rst) begin
            for (int i = 0; i < N_INSTR; i++) begin
                bid_occ[i] <= '0;  ask_occ[i] <= '0;  base[i] <= '0;
                t_bpx[i] <= '0;  t_bqty[i] <= '0;  t_apx[i] <= '0;  t_aqty[i] <= '0;
            end
            tob_valid      <= 1'b0;
            tob_instrument <= '0;
            best_bid_px    <= '0;  best_bid_qty <= '0;
            best_ask_px    <= '0;  best_ask_qty <= '0;
            tob_crossed    <= 1'b0;
            rej_valid      <= 1'b0;
            rej_reason     <= '0;
            // (the qty memories need no reset: occ says which entries are valid)
        end else begin
            tob_valid <= 1'b0;
            rej_valid <= 1'b0;

            if (cfg_valid) begin
                if (cfg_instrument < N_INSTR) begin
                    base[cfg_ii]    <= cfg_base_px;
                    bid_occ[cfg_ii] <= '0;
                    ask_occ[cfg_ii] <= '0;
                    t_bpx[cfg_ii] <= '0;  t_bqty[cfg_ii] <= '0;
                    t_apx[cfg_ii] <= '0;  t_aqty[cfg_ii] <= '0;
                end

            end else if (msg_valid) begin
                if (!instr_ok) begin
                    rej_valid  <= 1'b1;
                    rej_reason <= REJ_INSTR;
                end else if (!in_range) begin
                    rej_valid  <= 1'b1;
                    rej_reason <= REJ_RANGE;
                end else begin
                    // update the book
                    bid_occ[ii] <= bid_row_n;
                    ask_occ[ii] <= ask_row_n;
                    if (msg_qty != 0) begin
                        if (msg_is_bid) bid_qty[{ii, idx}] <= msg_qty;
                        else            ask_qty[{ii, idx}] <= msg_qty;
                    end
                    t_bpx[ii] <= n_bpx;  t_bqty[ii] <= n_bqty;
                    t_apx[ii] <= n_apx;  t_aqty[ii] <= n_aqty;

                    // report only if this instrument's top of book changed
                    if (changed) begin
                        tob_valid      <= 1'b1;
                        tob_instrument <= msg_instrument;
                        best_bid_px    <= n_bpx;  best_bid_qty <= n_bqty;
                        best_ask_px    <= n_apx;  best_ask_qty <= n_aqty;
                        tob_crossed    <= crossed_n;
                    end
                end
            end
        end
    end

endmodule
