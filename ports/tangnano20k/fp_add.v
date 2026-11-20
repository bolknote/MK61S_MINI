// Binary32 add/subtract, round to nearest even. Each register boundary splits
// a different stage of alignment, addition, normalization and rounding.
module tang_fp_add (
    input wire clk, resetn, start, subtract,
    input wire [31:0] a, b,
    output wire complete,
    output reg [31:0] result
);
    wire [31:0] effective_b = {b[31]^subtract,b[30:0]};
    wire swap = a[30:0] < b[30:0];
    wire na = a[30:23] == 255, nb = b[30:23] == 255;
    wire invalid = (na && a[22:0] != 0) || (nb && b[22:0] != 0) ||
                  (na && nb && a[31] != effective_b[31]);
    reg [7:0] valid;
    reg [7:0] special;
    reg [31:0] exceptional [0:7];
    reg [31:0] larger, smaller;
    reg [7:0] alignment, alignment_low;
    reg [26:0] large_significand [0:2];
    reg [26:0] small_significand [0:2];
    reg [7:0] exponent [0:4];
    reg [4:0] negative, opposite;
    reg [27:0] summed, sum_for_norm;
    reg [4:0] leading;
    reg [26:0] normalized;
    reg [8:0] normalized_exponent;
    reg result_sign;
    wire [4:0] zero_count;
    countLeadingZeros #(27,5) scan(summed[26:0], zero_count);
    wire [4:0] bounded_shift = leading >= exponent[4] ? exponent[4]-1'b1 : leading;
    wire [7:0] final_exponent = normalized[26] ? normalized_exponent[7:0] : 8'b0;
    wire round_up = normalized[2] && (normalized[1] || normalized[0] || normalized[3]);
    assign complete = valid[7];

    function [26:0] shift_near;
        input [26:0] significand;
        input [2:0] shift;
        reg [26:0] s;
        begin
            s = significand;
            if (shift[0]) s = {1'b0,s[26:2],|s[1:0]};
            if (shift[1]) s = {2'b0,s[26:3],|s[2:0]};
            if (shift[2]) s = {4'b0,s[26:5],|s[4:0]};
            shift_near = s;
        end
    endfunction

    function [26:0] shift_far;
        input [26:0] significand;
        input [4:0] shift;
        reg [26:0] s;
        begin
            s = significand;
            if (shift[0]) s = {8'b0,s[26:9],|s[8:0]};
            if (shift[1]) s = {16'b0,s[26:17],|s[16:0]};
            if (shift[4:2] != 0) s = {26'b0,|s};
            shift_far = s;
        end
    endfunction

    integer i;
    always @(posedge clk) begin
        valid <= resetn ? {valid[6:0],start} : 0;
        special <= {special[6:0],na||nb};
        exceptional[0] <= invalid ? 32'h7fc00000 : na ? a : effective_b;
        for (i=1; i<8; i=i+1) exceptional[i] <= exceptional[i-1];
        if (start) begin
            larger <= swap ? effective_b : a;
            smaller <= swap ? a : effective_b;
        end
        if (valid[0]) begin
            exponent[0] <= larger[30:23] == 0 ? 8'd1 : larger[30:23];
            alignment <= (larger[30:23] == 0 ? 8'd1 : larger[30:23]) -
                         (smaller[30:23] == 0 ? 8'd1 : smaller[30:23]);
            large_significand[0] <= {larger[30:23] != 0,larger[22:0],3'b0};
            small_significand[0] <= {smaller[30:23] != 0,smaller[22:0],3'b0};
            negative[0] <= larger[31];
            opposite[0] <= larger[31] != smaller[31];
        end
        for (i=1;i<5;i=i+1) begin
            exponent[i] <= exponent[i-1]; negative[i] <= negative[i-1]; opposite[i] <= opposite[i-1];
        end
        if (valid[1]) begin
            large_significand[1] <= large_significand[0];
            small_significand[1] <= shift_near(small_significand[0],alignment[2:0]);
            alignment_low <= alignment;
        end
        if (valid[2]) begin
            large_significand[2] <= large_significand[1];
            small_significand[2] <= shift_far(small_significand[1],alignment_low[7:3]);
        end
        if (valid[3]) summed <= opposite[2] ?
            {1'b0,large_significand[2]}-{1'b0,small_significand[2]} :
            {1'b0,large_significand[2]}+{1'b0,small_significand[2]};
        if (valid[4]) begin sum_for_norm <= summed; leading <= zero_count; end
        if (valid[5]) begin
            normalized <= sum_for_norm[27] ? {sum_for_norm[27:2],|sum_for_norm[1:0]} :
                                             sum_for_norm[26:0] << bounded_shift;
            normalized_exponent <= sum_for_norm[27] ? {1'b0,exponent[4]}+1'b1 :
                                                                      {1'b0,exponent[4]}-bounded_shift;
            result_sign <= negative[4] && (sum_for_norm != 0 || !opposite[4]);
        end
        if (valid[6]) begin
            if (special[6]) result <= exceptional[6];
            else if (normalized_exponent == 255) result <= {result_sign,8'hff,23'b0};
            else result <= {result_sign,final_exponent,normalized[25:3]}+round_up;
        end
    end
endmodule
