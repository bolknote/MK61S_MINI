// Hardware sequencer for the MKA transformer schedule. The only runtime inputs
// are a token ID and a flag selecting prefill or decode. Exported instructions
// describe whole tensor operations, including their SDRAM word addresses.
module tang_model (
    input wire clk, resetn, start, rewind,
    input wire [15:0] token,
    input wire output_logits,
    output wire busy,
    output reg done,
    output reg [7:0] status,
    output wire [31:0] outcome,
    output reg [31:0] checksum, cycles,
    output wire memory_request, memory_write,
    output reg [20:0] memory_address,
    output reg [31:0] memory_data,
    input wire memory_complete,
    input wire [31:0] memory_result,
    output wire dot_valid,
    output wire [31:0] dot_weights,
    output wire [63:0] dot_activations,
    input wire dot_ready,
    input wire signed [14:0] dot_result
);
    localparam [7:0]
        IDLE=0, HEADER=1, HEADER_WORD=2, CHECK_HEADER=3, FETCH=4, INSTRUCTION_WORD=5,
        EXECUTE=6, READ_EXT=7, WRITE_EXT=8, READ_RAM=9, WRITE_RAM=10, FP_START=11, FP_WAIT=12,
        EMBED_SCALE=13, EMBED_NEXT=14, EMBED_CONVERT=15, EMBED_SCALE_VALUE=16, EMBED_STORE=17, EMBED_ADVANCE=18,
        NORM_READ=19, NORM_SQUARE=20, NORM_ACCUMULATE=21, NORM_NEXT=22, NORM_EPSILON=23,
        NORM_SQRT=24, NORM_INVERSE=25, NORM_FACTOR=26, NORM_WEIGHT=27, NORM_VALUE=28,
        NORM_PRODUCT=29, NORM_SCALE=30, NORM_STORE=31, NORM_ADVANCE=32,
        QUANT_MAX_READ=33, QUANT_MAX_UPDATE=34, QUANT_SCALE=35, QUANT_READ=36,
        QUANT_DIVIDE=37, QUANT_STORE=38, MATRIX_WORD=39, MATRIX_STREAM=40,
        QUANT_PREPARE=41, QUANT_ALIGN=42,
        MATRIX_CONVERT=43, MATRIX_WEIGHT=44, MATRIX_ACTIVATION=45,
        MATRIX_ACCUMULATE=46, MATRIX_ADVANCE=47, MATRIX_NEXT_ROW=48,
        ROPE_READ=49, ROPE_SAVE=50, ROPE_COS=51, ROPE_SIN=52, ROPE_LC=53,
        ROPE_RS=54, ROPE_LEFT=55, ROPE_RC=56, ROPE_LS=57, ROPE_RIGHT=58, ROPE_STORE=59, ROPE_NEXT=60,
        KV_READ=61, KV_WORD=62, KV_NEXT=63,
        ATT_Q=64, ATT_K=65, ATT_PRODUCT=66, ATT_ACCUMULATE=67, ATT_NEXT=68, ATT_SCORE=69, ATT_SCORE_NEXT=70,
        SOFTMAX_READ=71, SOFTMAX_SUB=72, SOFTMAX_EXP=73, SOFTMAX_STORE=74,
        SOFTMAX_ACCUMULATE=75, SOFTMAX_NEXT=76,
        VALUE_SCORE=77, VALUE_WEIGHT=78, VALUE_START=79, VALUE_HEAD=80, VALUE_MEMORY=81,
        VALUE_PRODUCT=82, VALUE_SUM=83, VALUE_STORE=84, VALUE_NEXT=85,
        ADD_READ=86, ADD_RESULT=87, ADD_WRITE=88, ADD_NEXT=89,
        SILU_READ=90, SILU_EXP=91, SILU_ADD=92, SILU_DIVIDE=93, SILU_PRODUCT=94, SILU_STORE=95;
    localparam [2:0] FADD=0, FSUB=1, FMUL=2, FDIV=3, FSQRT=4, I2F=5, FEXP=6;
    localparam [31:0] ONE=32'h3f800000, NEG_MAX=32'hff7fffff;
    localparam [31:0] INV_SQRT_32=32'h3e3504f3;
    localparam [11:0] SCORES=1536;

    reg [7:0] state, continuation;
    reg [31:0] configuration [0:5];
    reg [31:0] descriptor [0:3];
    reg [2:0] field;
    reg [20:0] pc, cursor;
    reg [8:0] instructions_left;
    reg [10:0] position, time_index;
    reg [15:0] input_token, best_token, row;
    reg want_logits;
    reg [11:0] i, group_offset;
    reg [5:0] group_number;
    reg [2:0] head;
    reg [2:0] matrix_words, dot_groups;
    reg [31:0] accumulator, factor, max_value, left_value, right_value, cosine, sine;
    reg [31:0] ext_word;
    reg signed [16:0] integer_sum;
    reg [63:0] pack;
    reg [63:0] quantized [0:47];
    reg [31:0] act_scale [0:11];
    reg [23:0] quant_mantissa;
    reg [4:0] quant_shift;
    reg [8:0] quant_aligned;
    reg quant_negative, quant_zero, quant_saturated;

    wire [7:0] opcode = descriptor[0][7:0];
    wire [11:0] source = descriptor[1][11:0];
    wire [11:0] destination = descriptor[1][27:16];
    wire [20:0] address = descriptor[2][20:0];
    wire [11:0] width = descriptor[3][11:0];
    wire [15:0] rows = descriptor[3][31:16];
    wire [20:0] rotary_base = address + {5'b0,position,5'b0};
    wire [20:0] attention_base = address + {3'b0,time_index,7'b0} + (head[1] ? 21'd32 : 21'd0);
    wire [11:0] source_head = source + {4'b0,head,5'b0};
    wire [11:0] output_head = destination + {4'b0,head,5'b0};
    wire [3:0] embed_code = ext_word[4*i[2:0] +: 4] ^ 4'h8;
    wire [31:0] magnitude = {1'b0,ram_a[30:0]};
    wire [31:0] group_max = magnitude > max_value ? magnitude : max_value;

    (* ram_style="block" *) reg [31:0] scratch [0:4095];
    reg [11:0] ram_address_a, ram_address_b;
    reg [31:0] ram_a, ram_b, write_value;
    always @(posedge clk) begin
        if (state == WRITE_RAM) scratch[ram_address_a] <= write_value;
        else ram_a <= scratch[ram_address_a];
        ram_b <= scratch[ram_address_b];
    end

    reg [31:0] fp_a, fp_b;
    reg [2:0] fp_operation;
    wire fp_complete;
    wire [31:0] fp_value;
    tang_fp32 fp(clk, resetn, state == FP_START, fp_operation, fp_a, fp_b, fp_complete, fp_value);

    assign busy = state != IDLE;
    assign outcome = {5'b0,position,best_token};
    assign memory_request = state == READ_EXT || state == WRITE_EXT ||
                            (state == MATRIX_STREAM && matrix_words < 5);
    assign memory_write = state == WRITE_EXT;
    assign dot_valid = state == MATRIX_STREAM && memory_complete && matrix_words < 4;
    assign dot_weights = memory_result;
    assign dot_activations = quantized[{group_number[3:0],matrix_words[1:0]}];

    function [31:0] ordered;
        input [31:0] value;
        ordered = value[30:0] == 0 ? 32'h80000000 : value[31] ? ~value : value ^ 32'h80000000;
    endfunction

    wire [7:0] quant_magnitude = quant_zero ? 8'd0 : quant_saturated ? 8'd127 :
                                quant_aligned[8:1] + quant_aligned[0];
    wire [7:0] quant_value = quant_negative ? -quant_magnitude : quant_magnitude;
    wire [63:0] pack_next = {quant_value,pack[63:8]};

    task read_ext;
        input [20:0] word_address;
        input [7:0] next_state;
        begin memory_address <= word_address; continuation <= next_state; state <= READ_EXT; end
    endtask
    task write_ext;
        input [20:0] word_address;
        input [31:0] word_value;
        input [7:0] next_state;
        begin memory_address <= word_address; memory_data <= word_value;
              continuation <= next_state; state <= WRITE_EXT; end
    endtask
    task read_ram;
        input [11:0] first, second;
        input [7:0] next_state;
        begin ram_address_a <= first; ram_address_b <= second; continuation <= next_state; state <= READ_RAM; end
    endtask
    task put_ram;
        input [11:0] dest;
        input [31:0] value;
        input [7:0] next_state;
        begin ram_address_a <= dest; write_value <= value; continuation <= next_state; state <= WRITE_RAM; end
    endtask
    task calculate;
        input [2:0] operation;
        input [31:0] a, b;
        input [7:0] next_state;
        begin fp_operation <= operation; fp_a <= a; fp_b <= b; continuation <= next_state; state <= FP_START; end
    endtask
    task advance;
        begin pc <= pc+4; field <= 0; instructions_left <= instructions_left-1'b1; state <= FETCH; end
    endtask
    task finish;
        input [7:0] code;
        begin status <= code; done <= 1; state <= IDLE; end
    endtask

    always @(posedge clk) begin
        done <= 0;
        if (!resetn) begin
            state <= IDLE;
            position <= 0;
            cycles <= 0;
        end else begin
            if (busy) cycles <= cycles + 1'b1;
            case (state)
                IDLE: if (rewind) position <= 0;
                    else if (start) begin
                        input_token <= token; want_logits <= output_logits;
                        field <= 0; cycles <= 0; best_token <= 0; checksum <= 2166136261;
                        state <= HEADER;
                    end
                HEADER: read_ext({18'b0,field},HEADER_WORD);
                HEADER_WORD: begin
                    configuration[field] <= ext_word;
                    field <= field+1'b1;
                    state <= field == 5 ? CHECK_HEADER : HEADER;
                end
                CHECK_HEADER: begin
                    if (configuration[0] != 32'h32474e54 || configuration[2] != 1024 ||
                        configuration[1] == 0 || configuration[1] > 65535 || configuration[4] >= 21'h88000 ||
                        configuration[5] == 0 || configuration[5] > 184) finish(4);
                    else if (position == 1024 || input_token >= configuration[1]) finish(5);
                    else begin pc <= configuration[4][20:0]; instructions_left <= configuration[5][8:0];
                               field <= 0; state <= FETCH; end
                end
                FETCH: if (!instructions_left) finish(4);
                       else read_ext(pc+{18'b0,field}, INSTRUCTION_WORD);
                INSTRUCTION_WORD: begin
                    descriptor[field[1:0]] <= ext_word;
                    field <= field+1'b1;
                    state <= field == 3 ? EXECUTE : FETCH;
                end
                READ_EXT, WRITE_EXT: if (memory_complete) begin ext_word <= memory_result; state <= continuation; end
                READ_RAM, WRITE_RAM: state <= continuation;
                FP_START: state <= FP_WAIT;
                FP_WAIT: if (fp_complete) state <= continuation;

                EXECUTE: begin
                    i <= 0; group_offset <= 0; group_number <= 0; row <= 0; head <= 0;
                    time_index <= 0; accumulator <= 0; cursor <= address; max_value <= 0;
                    if (descriptor[0][8] && !want_logits) advance();
                    else case (opcode)
                        1: begin cursor <= address+input_token*21'd20; state <= EMBED_SCALE; end
                        2: state <= NORM_READ;
                        3,9: state <= QUANT_MAX_READ;
                        4: state <= ROPE_READ;
                        5: begin cursor <= address+{3'b0,position,7'b0}; state <= KV_READ; end
                        6: begin max_value <= NEG_MAX; state <= ATT_Q; end
                        7: state <= ADD_READ;
                        8: state <= SILU_READ;
                        10: begin position <= position+1'b1; finish(0); end
                        default: finish(4);
                    endcase
                end

                EMBED_SCALE: read_ext(cursor+4,EMBED_NEXT);
                EMBED_NEXT: begin factor <= ext_word; read_ext(cursor+{19'b0,i[4:3]},EMBED_CONVERT); end
                EMBED_CONVERT: calculate(I2F,{{28{embed_code[3]}},embed_code},0,EMBED_SCALE_VALUE);
                EMBED_SCALE_VALUE: calculate(FMUL,fp_value,factor,EMBED_STORE);
                EMBED_STORE: put_ram(destination+i,fp_value,EMBED_ADVANCE);
                EMBED_ADVANCE: if (i+1'b1 == width) advance();
                    else begin
                        i <= i+1'b1;
                        if (i[4:0] == 31) begin cursor <= cursor+5; state <= EMBED_SCALE; end
                        else read_ext(cursor+{19'b0,(i[4:0]+5'd1)>>3},EMBED_CONVERT);
                    end

                NORM_READ: read_ram(source+group_offset+i,0,NORM_SQUARE);
                NORM_SQUARE: calculate(FMUL,ram_a,ram_a,NORM_ACCUMULATE);
                NORM_ACCUMULATE: calculate(FADD,accumulator,fp_value,NORM_NEXT);
                NORM_NEXT: if (i+1'b1 == width) calculate(FDIV,fp_value,width == 32 ? 32'h42000000 : 32'h43000000,NORM_EPSILON);
                    else begin accumulator <= fp_value; i <= i+1'b1; state <= NORM_READ; end
                NORM_EPSILON: calculate(FADD,fp_value,configuration[3],NORM_SQRT);
                NORM_SQRT: calculate(FSQRT,fp_value,0,NORM_INVERSE);
                NORM_INVERSE: calculate(FDIV,ONE,fp_value,NORM_FACTOR);
                NORM_FACTOR: begin factor <= fp_value; i <= 0; state <= NORM_WEIGHT; end
                NORM_WEIGHT: read_ext(address+{9'b0,i},NORM_VALUE);
                NORM_VALUE: read_ram(source+group_offset+i,0,NORM_PRODUCT);
                NORM_PRODUCT: calculate(FMUL,ram_a,factor,NORM_SCALE);
                NORM_SCALE: calculate(FMUL,fp_value,ext_word,NORM_STORE);
                NORM_STORE: put_ram(destination+group_offset+i,fp_value,NORM_ADVANCE);
                NORM_ADVANCE: if (i+1'b1 != width) begin i <= i+1'b1; state <= NORM_WEIGHT; end
                    else if ({10'b0,group_number}+1'b1 == rows) advance();
                    else begin
                        group_number <= group_number+1'b1; group_offset <= group_offset+width;
                        i <= 0; accumulator <= 0; state <= NORM_READ;
                    end

                QUANT_MAX_READ: read_ram(source+group_offset+i,0,QUANT_MAX_UPDATE);
                QUANT_MAX_UPDATE: if (i == 31) calculate(FDIV,group_max,32'h42fe0000,QUANT_SCALE);
                    else begin max_value <= group_max; i <= i+1'b1; state <= QUANT_MAX_READ; end
                QUANT_SCALE: begin
                    factor <= fp_value; act_scale[group_number] <= fp_value; i <= 0; pack <= 0; state <= QUANT_READ;
                end
                QUANT_READ: read_ram(source+group_offset+i,0,QUANT_DIVIDE);
                QUANT_DIVIDE: calculate(FDIV, factor == 0 ? 32'b0 : ram_a, factor == 0 ? ONE : factor, QUANT_PREPARE);
                QUANT_PREPARE: begin
                    quant_mantissa <= {1'b1,fp_value[22:0]};
                    // For the in-range exponents, (149 - exponent) fits in
                    // five bits. Leave the first discarded bit for rounding.
                    quant_shift <= 5'd21 - fp_value[27:23];
                    quant_negative <= fp_value[31];
                    quant_zero <= fp_value[30:23] <= 8'd125;
                    quant_saturated <= fp_value[30:23] >= 8'd150;
                    state <= QUANT_ALIGN;
                end
                QUANT_ALIGN: begin
                    quant_aligned <= quant_mantissa >> quant_shift;
                    state <= QUANT_STORE;
                end
                QUANT_STORE: begin
                    pack <= pack_next;
                    if (i[2:0] == 7) quantized[{group_number[3:0],i[4:3]}] <= pack_next;
                    if (i != 31) begin i <= i+1'b1; state <= QUANT_READ; end
                    else if (group_offset+12'd32 != width) begin
                        group_offset <= group_offset+12'd32; group_number <= group_number+1'b1;
                        i <= 0; max_value <= 0; state <= QUANT_MAX_READ;
                    end else begin
                        group_number <= 0; accumulator <= 0;
                        max_value <= NEG_MAX; state <= MATRIX_WORD;
                    end
                end
                MATRIX_WORD: begin
                    memory_address <= cursor;
                    matrix_words <= 0;
                    dot_groups <= 0;
                    integer_sum <= 0;
                    state <= MATRIX_STREAM;
                end
                MATRIX_STREAM: begin
                    // Launch the next read as the previous word enters the DSP
                    // pipeline. The fifth word is the FP32 weight scale.
                    if (memory_complete) begin
                        memory_address <= memory_address + 1'b1;
                        matrix_words <= matrix_words + 1'b1;
                        if (matrix_words == 4) ext_word <= memory_result;
                    end
                    if (dot_ready) begin
                        integer_sum <= integer_sum + {{2{dot_result[14]}},dot_result};
                        dot_groups <= dot_groups + 1'b1;
                    end
                    if (matrix_words == 5 && dot_groups == 4) state <= MATRIX_CONVERT;
                end
                MATRIX_CONVERT: calculate(I2F,{{15{integer_sum[16]}},integer_sum},0,MATRIX_WEIGHT);
                MATRIX_WEIGHT: calculate(FMUL,fp_value,ext_word,MATRIX_ACTIVATION);
                MATRIX_ACTIVATION: calculate(FMUL,fp_value,act_scale[group_number],MATRIX_ACCUMULATE);
                MATRIX_ACCUMULATE: calculate(FADD,accumulator,fp_value,MATRIX_ADVANCE);
                MATRIX_ADVANCE: begin
                    accumulator <= fp_value;
                    cursor <= cursor+21'd5;
                    if ({6'b0,group_number}+1'b1 != (width>>5)) begin
                        group_number <= group_number+1'b1; state <= MATRIX_WORD;
                    end else if (fp_value[30:23] == 255) finish(6);
                    else begin
                        checksum <= (checksum ^ fp_value)*32'd16777619;
                        if (opcode == 9) begin
                            if (ordered(fp_value) > ordered(max_value)) begin max_value <= fp_value; best_token <= row; end
                            state <= MATRIX_NEXT_ROW;
                        end else put_ram(destination+row[11:0],fp_value,MATRIX_NEXT_ROW);
                    end
                end
                MATRIX_NEXT_ROW: if (row+1'b1 == rows) advance();
                    else begin row <= row+1'b1; group_number <= 0; accumulator <= 0; state <= MATRIX_WORD; end

                ROPE_READ: read_ram(source+group_offset+i,source+group_offset+i+12'd16,ROPE_SAVE);
                ROPE_SAVE: begin
                    left_value <= ram_a; right_value <= ram_b;
                    read_ext(rotary_base+{8'b0,i,1'b0},ROPE_COS);
                end
                ROPE_COS: begin cosine <= ext_word; read_ext(rotary_base+{8'b0,i,1'b1},ROPE_SIN); end
                ROPE_SIN: begin sine <= ext_word; calculate(FMUL,left_value,cosine,ROPE_LC); end
                ROPE_LC: begin accumulator <= fp_value; calculate(FMUL,right_value,sine,ROPE_RS); end
                ROPE_RS: calculate(FSUB,accumulator,fp_value,ROPE_LEFT);
                ROPE_LEFT: put_ram(destination+group_offset+i,fp_value,ROPE_RC);
                ROPE_RC: calculate(FMUL,right_value,cosine,ROPE_LS);
                ROPE_LS: begin accumulator <= fp_value; calculate(FMUL,left_value,sine,ROPE_RIGHT); end
                ROPE_RIGHT: calculate(FADD,accumulator,fp_value,ROPE_STORE);
                ROPE_STORE: put_ram(destination+group_offset+i+12'd16,fp_value,ROPE_NEXT);
                ROPE_NEXT: if (i != 15) begin i <= i+1'b1; state <= ROPE_READ; end
                    else if ({10'b0,group_number}+1'b1 == rows) advance();
                    else begin group_number <= group_number+1'b1; group_offset <= group_offset+12'd32;
                               i <= 0; state <= ROPE_READ; end

                KV_READ: read_ram(source+i,0,KV_WORD);
                KV_WORD: write_ext(cursor+{9'b0,i},ram_a,KV_NEXT);
                KV_NEXT: if (i+1'b1 == width) advance();
                    else begin i <= i+1'b1; state <= KV_READ; end

                ATT_Q: read_ram(source_head+i,0,ATT_K);
                ATT_K: read_ext(attention_base+{9'b0,i},ATT_PRODUCT);
                ATT_PRODUCT: calculate(FMUL,ram_a,ext_word,ATT_ACCUMULATE);
                ATT_ACCUMULATE: calculate(FADD,accumulator,fp_value,ATT_NEXT);
                ATT_NEXT: if (i == 31) calculate(FMUL,fp_value,INV_SQRT_32,ATT_SCORE);
                    else begin i <= i+1'b1; accumulator <= fp_value; state <= ATT_Q; end
                ATT_SCORE: begin
                    if (ordered(fp_value)>ordered(max_value)) max_value <= fp_value;
                    put_ram(SCORES+{1'b0,time_index},fp_value,ATT_SCORE_NEXT);
                end
                ATT_SCORE_NEXT: begin
                    i <= 0; accumulator <= 0;
                    if (time_index == position) begin time_index <= 0; state <= SOFTMAX_READ; end
                    else begin time_index <= time_index+1'b1; state <= ATT_Q; end
                end
                SOFTMAX_READ: read_ram(SCORES+{1'b0,time_index},0,SOFTMAX_SUB);
                SOFTMAX_SUB: calculate(FSUB,ram_a,max_value,SOFTMAX_EXP);
                SOFTMAX_EXP: calculate(FEXP,fp_value,0,SOFTMAX_STORE);
                SOFTMAX_STORE: put_ram(SCORES+{1'b0,time_index},fp_value,SOFTMAX_ACCUMULATE);
                SOFTMAX_ACCUMULATE: calculate(FADD,accumulator,fp_value,SOFTMAX_NEXT);
                SOFTMAX_NEXT: begin
                    accumulator <= fp_value;
                    if (time_index == position) begin time_index <= 0; state <= VALUE_SCORE; end
                    else begin time_index <= time_index+1'b1; state <= SOFTMAX_READ; end
                end
                VALUE_SCORE: read_ram(SCORES+{1'b0,time_index},0,VALUE_WEIGHT);
                VALUE_WEIGHT: calculate(FDIV,ram_a,accumulator,VALUE_START);
                VALUE_START: begin factor <= fp_value; i <= 0; state <= VALUE_HEAD; end
                VALUE_HEAD: read_ram(output_head+i,0,VALUE_MEMORY);
                VALUE_MEMORY: read_ext(attention_base+21'd64+{9'b0,i},VALUE_PRODUCT);
                VALUE_PRODUCT: calculate(FMUL,factor,ext_word,VALUE_SUM);
                VALUE_SUM: calculate(FADD,time_index == 0 ? 32'b0 : ram_a,fp_value,VALUE_STORE);
                VALUE_STORE: put_ram(output_head+i,fp_value,VALUE_NEXT);
                VALUE_NEXT: if (i != 31) begin i <= i+1'b1; state <= VALUE_HEAD; end
                    else if (time_index != position) begin time_index <= time_index+1'b1; state <= VALUE_SCORE; end
                    else if (head == 3) advance();
                    else begin head <= head+1'b1; time_index <= 0; i <= 0; accumulator <= 0;
                               max_value <= NEG_MAX; state <= ATT_Q; end

                ADD_READ: read_ram(destination+i,source+i,ADD_RESULT);
                ADD_RESULT: calculate(FADD,ram_a,ram_b,ADD_WRITE);
                ADD_WRITE: put_ram(destination+i,fp_value,ADD_NEXT);
                ADD_NEXT: if (i+1'b1 == width) advance();
                    else begin i <= i+1'b1; state <= opcode == 7 ? ADD_READ : SILU_READ; end
                SILU_READ: read_ram(destination+i,source+i,SILU_EXP);
                SILU_EXP: calculate(FEXP,ram_a ^ 32'h80000000,0,SILU_ADD);
                SILU_ADD: calculate(FADD,ONE,fp_value,SILU_DIVIDE);
                SILU_DIVIDE: calculate(FDIV,ram_a,fp_value,SILU_PRODUCT);
                SILU_PRODUCT: calculate(FMUL,fp_value,ram_b,SILU_STORE);
                SILU_STORE: put_ram(destination+i,fp_value,ADD_NEXT);
                default: finish(4);
            endcase
        end
    end
endmodule
