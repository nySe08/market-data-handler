// Milestone 0: "hello world" to prove the toolchain works.
// A simple counter with synchronous reset and enable.
module counter #(
    parameter int W = 8
) (
    input  logic         clk,
    input  logic         rst,   // synchronous, active-high
    input  logic         en,
    output logic [W-1:0] count
);

    always_ff @(posedge clk) begin
        if (rst)
            count <= '0;
        else if (en)
            count <= count + 1'b1;
    end

endmodule
