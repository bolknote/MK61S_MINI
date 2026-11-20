// Q55 range reduction by ln(2)/64. The table and degree-six polynomial are
// evaluated at fixed precision and packed to binary32 with ties to even.
module tang_exp32 (
    input wire clk, resetn, start,
    input wire [31:0] value,
    output wire complete,
    output reg [31:0] result
);
    localparam signed [63:0] ONE = 64'sd36028797018963968;
    localparam signed [63:0] LN2_BY64 = 64'sd390207173010335;
    localparam IDLE=0, BIN_OPERANDS=1, BIN_MUL=2, REDUCE_OPERANDS=3, REDUCE_MUL=4,
        REDUCED=5, TERM_OPERANDS=6, TERM_MUL=7, TERM_ADD=8, SCALE_OPERANDS=9,
        SCALE_MUL=10, NORMALIZE=11, PACK=12, RETURN=13, MUL_CROSS=14, MUL_LOW=15,
        MUL_HIGH=16, PACK_PREPARE=17, PACK_SHIFT=18, PACK_STICKY=19, PACK_ROUND=20;
    reg [4:0] stage, after_multiply;
    reg sign;
    reg [63:0] magnitude;
    reg signed [14:0] bin;
    reg signed [63:0] remainder, polynomial;
    reg [2:0] term;
    reg signed [63:0] multiplier_a, multiplier_b;
    wire signed [32:0] a_low = {1'b0, multiplier_a[31:0]};
    wire signed [32:0] b_low = {1'b0, multiplier_b[31:0]};
    wire signed [31:0] a_high = multiplier_a[63:32];
    wire signed [31:0] b_high = multiplier_b[63:32];
    reg [63:0] product_low;
    reg signed [63:0] product_high, low_high, high_low;
    reg signed [64:0] cross_product;
    reg [32:0] middle;
    reg signed [127:0] product;
    reg signed [9:0] power;
    reg [63:0] normalized;
    wire signed [10:0] biased = power + 11'sd127;
    reg [63:0] shifted, discarded_mask;
    reg [5:0] rounding_shift;
    reg [7:0] output_exponent;
    reg round_up, underflow, overflow;
    reg [24:0] rounded_significand;
    reg [56:0] scale_table [0:63];
    initial $readmemh("exp2.hex", scale_table);
    assign complete = stage == RETURN;

    function [63:0] fixed_abs;
        input [30:0] x;
        integer shift;
        reg [63:0] mantissa;
        begin
            shift = integer'(x[30:23]) - 95;
            mantissa = {40'b0, 1'b1, x[22:0]};
            if (x[30:23] == 0 || shift < -63) fixed_abs = 0;
            else if (shift < 0) fixed_abs = mantissa >> -shift;
            else fixed_abs = mantissa << shift;
        end
    endfunction

    function signed [63:0] coefficient;
        input [2:0] index;
        case (index)
            6: coefficient = 64'sd50039995859672;
            5: coefficient = 64'sd300239975158033;
            4: coefficient = 64'sd1501199875790165;
            3: coefficient = 64'sd6004799503160661;
            2: coefficient = 64'sd18014398509481984;
            default: coefficient = ONE;
        endcase
    endfunction

    // |x| < 128, so the rounded bin index fits in 15 bits.
    wire [14:0] rounded_bin = product[50:36] + product[35];
    wire signed [63:0] taylor_product = product >>> 55;

    always @(posedge clk) begin
        if (!resetn) stage <= IDLE;
        else case (stage)
            IDLE: if (start) begin
                if (value[30:23] >= 134) begin
                    result <= value[30:23] == 255 && value[22:0] != 0 ? 32'h7fc00000 :
                              value[31] ? 32'b0 : 32'h7f800000;
                    stage <= RETURN;
                end else begin
                    magnitude <= fixed_abs(value[30:0]);
                    sign <= value[31];
                    stage <= BIN_OPERANDS;
                end
            end
            BIN_OPERANDS: begin
                multiplier_a <= magnitude >> 35;
                multiplier_b <= 64'd6051102;
                stage <= BIN_MUL;
            end
            BIN_MUL, REDUCE_MUL, TERM_MUL, SCALE_MUL: begin
                product_low <= a_low * b_low;
                product_high <= a_high * b_high;
                low_high <= a_low * b_high;
                high_low <= a_high * b_low;
                after_multiply <= stage + 1'b1;
                stage <= MUL_CROSS;
            end
            MUL_CROSS: begin
                cross_product <= low_high + high_low;
                stage <= MUL_LOW;
            end
            MUL_LOW: begin
                middle <= {1'b0,product_low[63:32]} + {1'b0,cross_product[31:0]};
                stage <= MUL_HIGH;
            end
            MUL_HIGH: begin
                product <= {product_high + (cross_product >>> 32) + $signed({1'b0,middle[32]}),
                            middle[31:0], product_low[31:0]};
                stage <= after_multiply;
            end
            REDUCE_OPERANDS: begin
                bin <= sign ? -$signed(rounded_bin[14:0]) : $signed(rounded_bin[14:0]);
                multiplier_a <= rounded_bin;
                multiplier_b <= LN2_BY64;
                stage <= REDUCE_MUL;
            end
            REDUCED: begin
                remainder <= sign ? product[63:0] - magnitude : magnitude - product[63:0];
                polynomial <= coefficient(6);
                term <= 5;
                stage <= TERM_OPERANDS;
            end
            TERM_OPERANDS: begin multiplier_a <= remainder; multiplier_b <= polynomial; stage <= TERM_MUL; end
            TERM_ADD: begin
                polynomial <= taylor_product + coefficient(term);
                if (term == 0) stage <= SCALE_OPERANDS;
                else begin term <= term-1'b1; stage <= TERM_OPERANDS; end
            end
            SCALE_OPERANDS: begin
                multiplier_a <= {7'b0, scale_table[bin[5:0]]};
                multiplier_b <= polynomial;
                stage <= SCALE_MUL;
            end
            NORMALIZE: begin
                normalized <= taylor_product < ONE ? taylor_product << 1 : taylor_product;
                power <= (bin >>> 6) - (taylor_product < ONE ? 1 : 0);
                stage <= PACK_PREPARE;
            end
            PACK_PREPARE: begin
                rounding_shift <= biased <= 0 ? 6'd32 - biased[5:0] : 6'd31;
                output_exponent <= biased > 0 ? biased[7:0] - 1'b1 : 0;
                underflow <= biased <= -11'sd31;
                overflow <= biased >= 11'sd255;
                stage <= PACK_SHIFT;
            end
            PACK_SHIFT: begin
                shifted <= normalized >> rounding_shift;
                discarded_mask <= ~(64'hffff_ffff_ffff_ffff << rounding_shift);
                stage <= PACK_STICKY;
            end
            PACK_STICKY: begin
                round_up <= shifted[0] && (shifted[1] || |(normalized & discarded_mask));
                stage <= PACK_ROUND;
            end
            PACK_ROUND: begin
                rounded_significand <= {1'b0,shifted[24:1]} + round_up;
                stage <= PACK;
            end
            PACK: begin
                result <= overflow ? 32'h7f800000 : underflow ? 32'b0 :
                          {1'b0,output_exponent,23'b0} + {7'b0,rounded_significand};
                stage <= RETURN;
            end
            RETURN: stage <= IDLE;
            default: stage <= IDLE;
        endcase
    end
endmodule
