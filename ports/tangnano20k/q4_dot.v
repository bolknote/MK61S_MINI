// Eight Q4 codes (each stored as weight + 8) by eight signed activations.
// One group of eight can enter the pipeline every cycle.
module tang_q4_dot (
    input wire clk, resetn, valid,
    input wire [31:0] weights,
    input wire [63:0] activations,
    output reg ready,
    output wire signed [14:0] sum
);
    reg products_valid;
    reg signed [11:0] products [0:7];
    reg signed [13:0] lo, hi;
    assign sum = {lo[13], lo} + {hi[13], hi};

    always @(posedge clk) begin
        products_valid <= resetn && valid;
        ready <= resetn && products_valid;
        if (products_valid) begin
            lo <= {{2{products[0][11]}}, products[0]} + {{2{products[1][11]}}, products[1]} +
                  {{2{products[2][11]}}, products[2]} + {{2{products[3][11]}}, products[3]};
            hi <= {{2{products[4][11]}}, products[4]} + {{2{products[5][11]}}, products[5]} +
                  {{2{products[6][11]}}, products[6]} + {{2{products[7][11]}}, products[7]};
        end
    end

    genvar lane;
    generate for (lane = 0; lane < 8; lane = lane + 1) begin: multiply_lane
        wire signed [3:0] weight = weights[lane*4 +: 4] ^ 4'h8;
        wire signed [7:0] activation = activations[lane*8 +: 8];
        always @(posedge clk) if (valid) products[lane] <= weight * activation;
    end endgenerate
endmodule
