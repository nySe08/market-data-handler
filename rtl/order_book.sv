// Milestone 4: the order book = one bid side + one ask side.
// Takes decoded messages from msg_decoder, outputs the top of book.
module order_book #(
    parameter int N = 8
) (
    input  logic        clk,
    input  logic        rst,

    // decoded message (from msg_decoder)
    input  logic        msg_valid,
    input  logic        msg_is_bid,
    input  logic [31:0] msg_price,
    input  logic [31:0] msg_qty,

    // top of book
    output logic        tob_valid,     // 1-cycle pulse: best bid or best ask changed
    output logic [31:0] best_bid_px,
    output logic [31:0] best_bid_qty,
    output logic [31:0] best_ask_px,
    output logic [31:0] best_ask_qty
);

    logic bid_changed, ask_changed;
    logic bid_valid_unused, ask_valid_unused;

    book_side #(.IS_BID(1'b1), .N(N)) u_bid (
        .clk, .rst,
        .upd_valid    (msg_valid &&  msg_is_bid),
        .upd_px       (msg_price),
        .upd_qty      (msg_qty),
        .best_valid   (bid_valid_unused),
        .best_px      (best_bid_px),
        .best_qty     (best_bid_qty),
        .best_changed (bid_changed)
    );

    book_side #(.IS_BID(1'b0), .N(N)) u_ask (
        .clk, .rst,
        .upd_valid    (msg_valid && !msg_is_bid),
        .upd_px       (msg_price),
        .upd_qty      (msg_qty),
        .best_valid   (ask_valid_unused),
        .best_px      (best_ask_px),
        .best_qty     (best_ask_qty),
        .best_changed (ask_changed)
    );

    assign tob_valid = bid_changed | ask_changed;

endmodule
