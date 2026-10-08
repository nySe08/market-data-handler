// Top level: raw Ethernet frame bytes in -> top of book out.
//
//   s_* bytes -> eth_ip_udp_parser -> msg_decoder -> price_book -> tob_*
//                  (1 cycle)           (1 cycle)      (1 cycle)
//
// v2: uses price_book (no lost levels, multiple instruments, crossed flag).
// The v1 book (order_book.sv / book_side.sv) is kept in the repo for reference.
module market_data_handler #(
    parameter logic [15:0] UDP_PORT = 16'd26400,
    parameter int          N_INSTR  = 4,
    parameter int          W        = 256
) (
    input  logic        clk,
    input  logic        rst,

    // configuration: price window per instrument (start of day)
    input  logic        cfg_valid,
    input  logic [15:0] cfg_instrument,
    input  logic [31:0] cfg_base_px,

    // raw frame bytes
    input  logic        s_tvalid,
    input  logic [7:0]  s_tdata,
    input  logic        s_tlast,

    // top of book
    output logic        tob_valid,
    output logic [15:0] tob_instrument,
    output logic [31:0] best_bid_px,
    output logic [31:0] best_bid_qty,
    output logic [31:0] best_ask_px,
    output logic [31:0] best_ask_qty,
    output logic        tob_crossed,

    // rejected messages
    output logic        rej_valid,
    output logic [1:0]  rej_reason
);

    // parser -> decoder
    logic       p_tvalid, p_tlast;
    logic [7:0] p_tdata;

    // decoder -> book
    logic        msg_valid, msg_is_bid;
    logic [15:0] msg_instrument;
    logic [31:0] msg_price, msg_qty, msg_seq;

    eth_ip_udp_parser #(.UDP_PORT(UDP_PORT)) u_parser (
        .clk, .rst,
        .s_tvalid, .s_tdata, .s_tlast,
        .m_tvalid (p_tvalid), .m_tdata (p_tdata), .m_tlast (p_tlast)
    );

    msg_decoder u_decoder (
        .clk, .rst,
        .s_tvalid (p_tvalid), .s_tdata (p_tdata), .s_tlast (p_tlast),
        .msg_valid, .msg_is_bid, .msg_instrument,
        .msg_price, .msg_qty, .msg_seq
    );

    price_book #(.N_INSTR(N_INSTR), .W(W)) u_book (
        .clk, .rst,
        .cfg_valid, .cfg_instrument, .cfg_base_px,
        .msg_valid, .msg_is_bid, .msg_instrument, .msg_price, .msg_qty,
        .tob_valid, .tob_instrument,
        .best_bid_px, .best_bid_qty, .best_ask_px, .best_ask_qty,
        .tob_crossed, .rej_valid, .rej_reason
    );

endmodule
