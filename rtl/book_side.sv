// Milestone 4: ONE side of the order book (bid or ask), N price levels.
//
// The levels are kept SORTED, best price at index 0:
//   bid side: highest price first      ask side: lowest price first
// Empty levels (vld = 0) are always at the end.
//
// Every update is handled in ONE clock cycle using parallel comparators:
//   qty > 0, price already in book -> update its qty
//   qty > 0, new price             -> insert it in sorted position
//                                     (entries behind it shift down one place;
//                                      if the book was full, the worst falls off)
//   qty = 0, price in book         -> remove it (entries behind it shift up)
module book_side #(
    parameter bit IS_BID = 1'b1,
    parameter int N      = 8
) (
    input  logic        clk,
    input  logic        rst,

    input  logic        upd_valid,     // an update for THIS side
    input  logic [31:0] upd_px,
    input  logic [31:0] upd_qty,

    output logic        best_valid,    // side is not empty
    output logic [31:0] best_px,       // 0 if empty
    output logic [31:0] best_qty,      // 0 if empty
    output logic        best_changed   // 1-cycle pulse: best level changed
);

    // ---------------- current book (registers) ----------------
    logic [31:0] px  [N];
    logic [31:0] qty [N];
    logic        vld [N];

    // ---------------- next book (combinational) ---------------
    logic [31:0] px_n  [N];
    logic [31:0] qty_n [N];
    logic        vld_n [N];

    // ---------------- parallel comparisons --------------------
    // match[i]  : level i holds exactly the update's price
    // goes_before[i] : the update's price belongs BEFORE level i
    //             (level i is empty, or the new price is better)
    // Because the book is sorted, goes_before[] looks like 0..0 1..1 :
    // the first 1 is the insert position.
    logic [N-1:0] match, goes_before;
    always_comb begin
        for (int i = 0; i < N; i++) begin
            match[i]  = vld[i] && (px[i] == upd_px);
            goes_before[i] = !vld[i] || (IS_BID ? (upd_px > px[i]) : (upd_px < px[i]));
        end
    end

    logic any_match, do_update, do_remove, do_insert;
    assign any_match = |match;
    assign do_update = upd_valid &&  any_match && (upd_qty != 0);
    assign do_remove = upd_valid &&  any_match && (upd_qty == 0);
    assign do_insert = upd_valid && !any_match && (upd_qty != 0) && (|goes_before);

    // at_or_after_match[i] = the matched level is at index <= i
    logic [N-1:0] at_or_after_match;
    assign at_or_after_match[0] = match[0];
    for (genvar g = 1; g < N; g++) begin : g_prefix_or
        assign at_or_after_match[g] = at_or_after_match[g-1] | match[g];
    end

    // ---------------- next-state logic, entry by entry --------
    // Each entry only looks at itself and its two neighbours:
    // that is what keeps this fast (small muxes, no long chains).
    always_comb begin
        for (int i = 0; i < N; i++) begin
            // default: keep
            px_n[i]  = px[i];
            qty_n[i] = qty[i];
            vld_n[i] = vld[i];

            if (do_update && match[i]) begin
                qty_n[i] = upd_qty;

            end else if (do_remove && at_or_after_match[i]) begin
                // close the gap: take the entry behind me
                if (i < N-1) begin
                    px_n[i]  = px[i+1];
                    qty_n[i] = qty[i+1];
                    vld_n[i] = vld[i+1];
                end else begin
                    vld_n[i] = 1'b0;          // last slot becomes empty
                end

            end else if (do_insert && goes_before[i]) begin
                if (i == 0 || !goes_before[i-1]) begin
                    // I am the insert position: load the new level
                    px_n[i]  = upd_px;
                    qty_n[i] = upd_qty;
                    vld_n[i] = 1'b1;
                end else begin
                    // behind the insert position: shift down by one
                    px_n[i]  = px[i-1];
                    qty_n[i] = qty[i-1];
                    vld_n[i] = vld[i-1];
                end
            end
        end
    end

    // ---------------- registers --------------------------------
    always_ff @(posedge clk) begin
        if (rst) begin
            for (int i = 0; i < N; i++) begin
                px[i]  <= '0;
                qty[i] <= '0;
                vld[i] <= 1'b0;
            end
            best_changed <= 1'b0;
        end else begin
            for (int i = 0; i < N; i++) begin
                px[i]  <= px_n[i];
                qty[i] <= qty_n[i];
                vld[i] <= vld_n[i];
            end
            // compare the NEW best level with the CURRENT one
            best_changed <= upd_valid &&
                            ((vld_n[0] != vld[0]) ||
                             (vld_n[0] && (px_n[0] != px[0] || qty_n[0] != qty[0])));
        end
    end

    // ---------------- outputs ----------------------------------
    assign best_valid = vld[0];
    assign best_px    = vld[0] ? px[0]  : '0;
    assign best_qty   = vld[0] ? qty[0] : '0;

endmodule
