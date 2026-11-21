// Hardware sequencer for the MKA transformer schedule. A prefill batch advances
// all of its positions through one instruction before fetching the next one.
module tang_model #(
    parameter PREFILL_LANES = 4
) (
    input wire clk, resetn, start, rewind,
    input wire [PREFILL_LANES*16-1:0] tokens,
    input wire [2:0] token_count,
    input wire output_logits,
    input wire [4:0] allowed_count,
    input wire [10:0] seek_position,
    output wire busy,
    output reg done,
    output reg [7:0] status,
    output wire [31:0] outcome,
    output wire [31:0] checksum,
    output wire [PREFILL_LANES*32-1:0] position_checksums,
    output reg [31:0] cycles,
    output wire memory_request, memory_write,
    output wire memory_burst,
    output reg [20:0] memory_address,
    output reg [31:0] memory_data,
    input wire memory_complete,
    input wire [31:0] memory_result,
    output reg dot_valid,
    output reg [31:0] dot_weights,
    output wire [PREFILL_LANES*64-1:0] dot_activations,
    input wire dot_ready,
    input wire [PREFILL_LANES*15-1:0] dot_results
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
        VALUE_SCORE=77, VALUE_WEIGHT=78, VALUE_START=79, VALUE_RESULT_READ=80, VALUE_STREAM=81,
        VALUE_STORE=84,
        ADD_READ=86, ADD_RESULT=87, ADD_WRITE=88, ADD_NEXT=89,
        SILU_READ=90, SILU_EXP=91, SILU_ADD=92, SILU_DIVIDE=93, SILU_PRODUCT=94, SILU_STORE=95,
        CHECK_TOKENS=96, MATRIX_NEXT_LANE=97, READ_PAIR_FIRST=98, READ_PAIR_SECOND=99,
        READ_RAM_RESULT=100, READ_PAIR_RESULT=101, ATT_PREFETCH=102,
        EMBED_ADDRESS=104, KV_ADDRESS=105, CHECK_LAYOUT=106, BEST_COMPARE=107, BEST_COMMIT=108,
        QUANT_MAX_COMMIT=109, ADVANCE_POSITION=110, ADVANCE_INSTRUCTION=111, FINISH=112,
        CHECK_TOKEN_RANGE=113, ALLOWED_READ=114, ALLOWED_TOKEN=115,
        ALLOWED_OFFSET=116, ALLOWED_ROW=117, VALUE_RESULT_NEXT=118, VALUE_RESULT_WAIT=119;
    localparam [2:0] FADD=0, FSUB=1, FMUL=2, FDIV=3, FSQRT=4, I2F=5, FEXP=6;
    localparam [31:0] ONE=32'h3f800000, NEG_MAX=32'hff7fffff;
    localparam [31:0] INV_SQRT_32=32'h3e3504f3;
    localparam [11:0] SCORES=1536;
    // Last 64 bytes of SDRAM, beyond all supported model and KV allocations.
    localparam [20:0] ALLOWED_ADDRESS=21'h1ffff0;
    localparam LANE_BITS = PREFILL_LANES <= 2 ? 1 : $clog2(PREFILL_LANES);
    localparam VECTOR_ADDR_BITS = $clog2(PREFILL_LANES*1536);

    localparam STATE_COUNT = VALUE_RESULT_WAIT + 1;
    // Decode the continuation when a sub-operation starts. A returning SDRAM
    // word or FP result can then select its next state without a binary decoder.
    reg [STATE_COUNT-1:0] state, continuation;
    function [STATE_COUNT-1:0] state_bit;
        input [7:0] index;
        begin state_bit = {{(STATE_COUNT-1){1'b0}},1'b1} << index; end
    endfunction
    reg [31:0] configuration [0:5];
    reg [31:0] descriptor [0:3];
    reg [2:0] field;
    reg [20:0] pc, cursor, embedding_offset;
    reg [8:0] instructions_left;
    reg [10:0] next_position, position, time_index;
    reg [PREFILL_LANES*16-1:0] input_tokens;
    reg [15:0] checked_token;
    reg [20:0] embedding_offsets [0:PREFILL_LANES-1];
    reg [2:0] batch_count;
    reg layout_valid, context_fits;
    reg [LANE_BITS-1:0] lane, last_lane;
    reg [15:0] best_token, row, final_row;
    reg [11:0] final_element, final_quant_offset;
    reg [6:0] final_group;
    reg last_element, last_group, last_quant_group, last_row, last_row_group;
    reg want_logits;
    reg [4:0] allowed_rows, allowed_index;
    reg masked_head;
    reg [20:0] row_offset;
    reg [11:0] i, group_offset;
    reg [5:0] group_number;
    reg [2:0] head;
    reg [2:0] matrix_words, dot_groups;
    reg [31:0] accumulator, factor, max_value, left_value, right_value, cosine, sine;
    reg [31:0] candidate_key, maximum_key;
    reg candidate_is_larger, magnitude_is_larger;
    reg [31:0] ext_word;
    reg [31:0] prefetched_word;
    reg prefetch_pending, prefetch_ready;
    wire signed [16:0] integer_sum [0:PREFILL_LANES-1];
    reg [31:0] matrix_accumulator [0:PREFILL_LANES-1];
    reg [31:0] lane_checksums [0:PREFILL_LANES-1];
    reg [31:0] hash_input, hash_output;
    reg [LANE_BITS-1:0] hash_input_lane, hash_output_lane;
    reg [1:0] hash_valid;
    reg [63:0] pack;
    reg [31:0] act_scale [0:PREFILL_LANES*16-1];
    reg [23:0] quant_mantissa;
    reg [4:0] quant_shift;
    reg [8:0] quant_aligned;
    reg quant_negative, quant_zero, quant_saturated;

    wire [7:0] opcode = descriptor[0][7:0];
    wire [11:0] source = descriptor[1][11:0];
    wire [11:0] destination = descriptor[1][27:16];
    wire [20:0] address = descriptor[2][20:0];
    wire [11:0] width = descriptor[3][11:0];
    wire [10:0] lane_position = next_position + {{(11-LANE_BITS){1'b0}},lane};
    wire [15:0] input_token = input_tokens[lane*16 +: 16];
    wire [15:0] allowed_token = allowed_index[0] ? ext_word[31:16] : ext_word[15:0];
    wire [20:0] rotary_cos = address + {5'b0,position,i[3:0],1'b0};
    wire [20:0] attention_key = address + {3'b0,time_index,1'b0,head[1],5'b0};
    wire [20:0] attention_value = address + {3'b0,time_index,1'b1,head[1],5'b0};
    wire [11:0] source_head = source + {4'b0,head,5'b0};
    wire [4:0] next_coordinate = i[4:0]+1'b1;
    wire [11:0] output_coordinate = destination + {4'b0,head,i[4:0]};
    wire [3:0] embed_code = ext_word[4*i[2:0] +: 4] ^ 4'h8;
    wire [31:0] magnitude = {1'b0,vector_word[30:0]};
    wire [31:0] group_max = magnitude_is_larger ? magnitude : max_value;

    // Each position needs 1536 words of vectors. A single read port is enough
    // with two reads for rotary, residual addition and SiLU, and fits six lanes.
    // Attention processes one position at a time and shares the score buffer.
    (* ram_style="block" *) reg [31:0] scratch [0:PREFILL_LANES*1536-1];
    (* ram_style="block" *) reg [31:0] scores [0:1023];
    reg [11:0] ram_address, pair_address;
    reg [31:0] vector_read, score_read, vector_word, first_operand, score_word, write_value;
    wire [LANE_BITS+1:0] lane_segment = {1'b0,lane,1'b0} + {{2{1'b0}},lane};
    wire [LANE_BITS+1:0] segment = lane_segment + {{LANE_BITS{1'b0}},ram_address[10:9]};
    wire [VECTOR_ADDR_BITS-1:0] vector_address = {segment,ram_address[8:0]};
    wire score_access = ram_address >= SCORES;
    wire [9:0] score_index = {~ram_address[9],ram_address[8:0]};
    always @(posedge clk) begin
        if (state[WRITE_RAM] && !score_access) scratch[vector_address] <= write_value;
        else vector_read <= scratch[vector_address];
        if (state[WRITE_RAM] && score_access) scores[score_index] <= write_value;
        else score_read <= scores[score_index];
        vector_word <= vector_read;
        score_word <= score_read;
    end

    reg [31:0] fp_a, fp_b;
    reg [2:0] fp_operation;
    wire fp_complete;
    wire [31:0] fp_value;
    // The query dot product feeds its sum back in order. Each coordinate of V
    // has its own accumulator, and all 32 sums are written before the next
    // time step reads them. Products and add results retire in address order.
    (* ram_style="block" *) reg [31:0] value_accumulators [0:31];
    reg [31:0] value_read, value_word, product_read, product_word;
    reg [5:0] value_fetched;
    reg [4:0] value_product_index, value_store_index;
    reg [1:0] value_product_valid;
    reg add_pending;
    wire value_request = state[VALUE_STREAM] && value_fetched < 32;
    wire value_input = value_request && memory_complete;
    wire value_product_done;
    wire [31:0] value_product;
    wire attention_add_complete;
    wire [31:0] attention_sum;
    wire add_ready = !add_pending || attention_add_complete;
    wire value_add = value_product_valid[1];
    wire query_add = add_ready && state[ATT_ACCUMULATE];
    wire value_retire = state[VALUE_STREAM] && attention_add_complete;
    wire [31:0] attention_base = value_add ? (time_index == 0 ? 32'b0 : value_word) :
                                 (add_pending ? attention_sum : accumulator);
    always @(posedge clk) begin
        value_product_valid <= resetn ? {value_product_valid[0],value_product_done} : 0;
        if (value_product_done || state[VALUE_RESULT_READ])
            value_read <= value_accumulators[value_product_done ? value_product_index : i[4:0]];
        value_word <= value_read;
        if (value_product_done) product_read <= value_product;
        product_word <= product_read;
        if (value_retire) value_accumulators[value_store_index] <= attention_sum;
    end
    tang_fp32 fp(.clk(clk), .resetn(resetn), .start(state[FP_START]),
                 .operation(fp_operation), .a(fp_a), .b(fp_b), .complete(fp_complete), .result(fp_value),
                 .add_start(query_add || value_add), .add_a(attention_base),
                 .add_b(value_add ? product_word : fp_value),
                 .add_complete(attention_add_complete), .add_value(attention_sum),
                 .mul_start(value_input), .mul_a(factor), .mul_b(memory_result),
                 .mul_complete(value_product_done), .mul_value(value_product));

    assign busy = !state[IDLE];
    assign outcome = {5'b0,next_position,best_token};
    assign checksum = lane_checksums[last_lane];
    assign memory_request = prefetch_pending || value_request || state[READ_EXT] || state[WRITE_EXT] ||
                            (state[MATRIX_STREAM] && matrix_words < 5);
    assign memory_write = state[WRITE_EXT];
    // Aligned V vectors consist of four complete eight-word SDRAM bursts.
    assign memory_burst = value_request && value_fetched[2:0] == 0 && memory_address[2:0] == 0;
    wire launch_dot = state[MATRIX_STREAM] && memory_complete && matrix_words < 4;
    wire hash_start = state[MATRIX_ADVANCE] && last_group && fp_value[30:23] != 8'hff;

    // These flags are consumed after the current element's RAM or FP stage.
    always @(posedge clk) begin
        last_element <= i == final_element;
        last_group <= {1'b0,group_number} == final_group;
        last_quant_group <= group_offset == final_quant_offset;
        last_row <= row == final_row;
        last_row_group <= {10'b0,group_number} == final_row;
    end

    function [31:0] ordered;
        input [31:0] value;
        ordered = value[30:0] == 0 ? 32'h80000000 : value[31] ? ~value : value ^ 32'h80000000;
    endfunction

    wire [7:0] quant_magnitude = quant_zero ? 8'd0 : quant_saturated ? 8'd127 :
                                quant_aligned[8:1] + quant_aligned[0];
    wire [7:0] quant_value = quant_negative ? -quant_magnitude : quant_magnitude;
    wire [63:0] pack_next = {quant_value,pack[63:8]};

    // Read one weight word from SDRAM and broadcast it to every DSP lane.
    // The quantized activations read in parallel with the weight register.
    always @(posedge clk) begin
        dot_valid <= resetn && launch_dot;
        if (launch_dot) dot_weights <= memory_result;
    end
    genvar p;
    generate for (p=0; p<PREFILL_LANES; p=p+1) begin: prefill_lane
        (* ram_style="block" *) reg [63:0] quantized [0:47];
        reg [63:0] activation_chunk;
        reg signed [16:0] dot_total;
        wire signed [14:0] dot_result = dot_results[p*15 +: 15];
        assign dot_activations[p*64 +: 64] = activation_chunk;
        assign integer_sum[p] = dot_total;
        assign position_checksums[p*32 +: 32] = lane_checksums[p];
        always @(posedge clk) begin
            if (state[QUANT_STORE] && i[2:0] == 7 && lane == p)
                quantized[{group_number[3:0],i[4:3]}] <= pack_next;
            if (launch_dot)
                activation_chunk <= quantized[{group_number[3:0],matrix_words[1:0]}];
            if (state[MATRIX_WORD]) dot_total <= 0;
            else if (state[MATRIX_STREAM] && dot_ready)
                dot_total <= dot_total + {{2{dot_result[14]}},dot_result};
        end
    end endgenerate

    task read_ext;
        input [20:0] word_address;
        input [7:0] next_state;
        begin memory_address <= word_address; continuation <= state_bit(next_state); state <= state_bit(READ_EXT); end
    endtask
    task write_ext;
        input [20:0] word_address;
        input [31:0] word_value;
        input [7:0] next_state;
        begin memory_address <= word_address; memory_data <= word_value;
              continuation <= state_bit(next_state); state <= state_bit(WRITE_EXT); end
    endtask
    task prefetch_next_attention_word;
        begin
            if (i != 31) begin
                memory_address <= memory_address + 1'b1;
                prefetch_pending <= 1;
            end
        end
    endtask
    task read_ram;
        input [11:0] word_address;
        input [7:0] next_state;
        begin ram_address <= word_address; continuation <= state_bit(next_state); state <= state_bit(READ_RAM); end
    endtask
    task read_pair;
        input [11:0] first, second;
        input [7:0] next_state;
        begin
            ram_address <= first; pair_address <= second; continuation <= state_bit(next_state); state <= state_bit(READ_PAIR_FIRST);
        end
    endtask
    task put_ram;
        input [11:0] dest;
        input [31:0] value;
        input [7:0] next_state;
        begin ram_address <= dest; write_value <= value; continuation <= state_bit(next_state); state <= state_bit(WRITE_RAM); end
    endtask
    task calculate;
        input [2:0] operation;
        input [31:0] a, b;
        input [7:0] next_state;
        begin fp_operation <= operation; fp_a <= a; fp_b <= b; continuation <= state_bit(next_state); state <= state_bit(FP_START); end
    endtask
    task finish;
        input [7:0] code;
        begin status <= code; state <= state_bit(FINISH); end
    endtask

    integer k;
    always @(posedge clk) begin
        done <= 0;
        if (!resetn) begin
            state <= state_bit(IDLE);
            next_position <= 0;
            cycles <= 0;
            prefetch_pending <= 0;
            prefetch_ready <= 0;
            hash_valid <= 0;
            add_pending <= 0;
        end else begin
            if (busy) cycles <= cycles + 1'b1;
            if (add_pending && attention_add_complete) begin
                add_pending <= 0;
                accumulator <= attention_sum;
            end
            if (query_add) add_pending <= 1;
            if (value_input) begin
                value_fetched <= value_fetched + 1'b1;
                memory_address <= memory_address + 1'b1;
            end
            if (value_product_done) value_product_index <= value_product_index + 1'b1;
            if (value_retire) value_store_index <= value_store_index + 1'b1;
            // Update each checksum while the sequencer writes the row and
            // starts the next one. The DSP sees only registered operands.
            hash_valid <= {hash_valid[0],hash_start};
            if (hash_start) begin
                hash_input <= lane_checksums[lane] ^ fp_value;
                hash_input_lane <= lane;
            end
            if (hash_valid[0]) begin
                hash_output <= hash_input * 32'd16777619;
                hash_output_lane <= hash_input_lane;
            end
            if (hash_valid[1]) lane_checksums[hash_output_lane] <= hash_output;
            if (prefetch_pending && memory_complete) begin
                prefetched_word <= memory_result;
                prefetch_pending <= 0;
                prefetch_ready <= 1;
            end
            (* parallel_case *) case (1'b1)
                state[IDLE]: if (rewind) begin
                        if (seek_position <= next_position) next_position <= seek_position;
                    end
                    else if (start) begin
                        input_tokens <= tokens; batch_count <= token_count; want_logits <= output_logits;
                        allowed_rows <= allowed_count;
                        last_lane <= token_count-1'b1; lane <= 0;
                        field <= 0; cycles <= 0; best_token <= 0;
                        for (k=0; k<PREFILL_LANES; k=k+1) lane_checksums[k] <= 2166136261;
                        state <= state_bit(HEADER);
                    end
                state[HEADER]: read_ext({18'b0,field},HEADER_WORD);
                state[HEADER_WORD]: begin
                    configuration[field] <= ext_word;
                    field <= field+1'b1;
                    state <= field == 5 ? state_bit(CHECK_HEADER) : state_bit(HEADER);
                end
                state[CHECK_HEADER]: begin
                    layout_valid <= configuration[0] == 32'h32474e54 && configuration[2] == 1024 &&
                                    configuration[1] != 0 && configuration[1] <= 65535 &&
                                    configuration[4] < 21'h88000 && configuration[5] != 0 &&
                                    configuration[5] <= 184;
                    context_fits <= batch_count != 0 && batch_count <= PREFILL_LANES &&
                                    next_position + {8'b0,batch_count} <= 1024;
                    state <= state_bit(CHECK_LAYOUT);
                end
                state[CHECK_LAYOUT]: begin
                    if (!layout_valid) finish(4);
                    else if (!context_fits) finish(5);
                    else state <= state_bit(CHECK_TOKENS);
                end
                state[CHECK_TOKENS]: begin checked_token <= input_token; state <= state_bit(CHECK_TOKEN_RANGE); end
                state[CHECK_TOKEN_RANGE]: begin
                    if (checked_token >= configuration[1][15:0]) finish(5);
                    else begin
                        embedding_offsets[lane] <= checked_token*21'd20;
                        if (lane != last_lane) begin lane <= lane+1'b1; state <= state_bit(CHECK_TOKENS); end
                        else begin
                            pc <= configuration[4][20:0]; instructions_left <= configuration[5][8:0];
                            lane <= 0; field <= 0; state <= state_bit(FETCH);
                        end
                    end
                end
                state[FETCH]: if (!instructions_left) finish(4);
                       else read_ext(pc+{18'b0,field}, INSTRUCTION_WORD);
                state[INSTRUCTION_WORD]: begin
                    descriptor[field[1:0]] <= ext_word;
                    // Decode loop limits once, keeping incrementers off the
                    // path from an inner-loop counter to the next state.
                    if (field == 3) begin
                        final_row <= ext_word[31:16] - 1'b1;
                        final_element <= ext_word[11:0] - 1'b1;
                        final_quant_offset <= ext_word[11:0] - 12'd32;
                        final_group <= ext_word[11:5] - 1'b1;
                    end
                    field <= field+1'b1;
                    state <= field == 3 ? state_bit(EXECUTE) : state_bit(FETCH);
                end
                state[READ_EXT], state[WRITE_EXT]: if (memory_complete) begin ext_word <= memory_result; state <= continuation; end
                state[READ_RAM]: state <= state_bit(READ_RAM_RESULT);
                state[READ_RAM_RESULT], state[WRITE_RAM]: state <= continuation;
                state[READ_PAIR_FIRST]: begin ram_address <= pair_address; state <= state_bit(READ_PAIR_SECOND); end
                state[READ_PAIR_SECOND]: state <= state_bit(READ_PAIR_RESULT);
                state[READ_PAIR_RESULT]: begin first_operand <= vector_word; state <= continuation; end
                state[FP_START]: state <= state_bit(FP_WAIT);
                state[FP_WAIT]: if (fp_complete) state <= continuation;
                state[FINISH]: begin done <= 1; state <= state_bit(IDLE); end
                state[ADVANCE_POSITION]: begin
                    if (lane == last_lane) state <= state_bit(ADVANCE_INSTRUCTION);
                    else begin lane <= lane+1'b1; state <= state_bit(EXECUTE); end
                end
                state[ADVANCE_INSTRUCTION]: begin
                    lane <= 0; pc <= pc+4; field <= 0;
                    instructions_left <= instructions_left-1'b1;
                    state <= state_bit(FETCH);
                end

                state[EXECUTE]: begin
                    i <= 0; group_offset <= 0; group_number <= 0; row <= 0; head <= 0;
                    masked_head <= opcode == 9 && allowed_rows != 0;
                    time_index <= 0; accumulator <= 0; cursor <= address; max_value <= 0;
                    position <= lane_position;
                    if (descriptor[0][8] && !want_logits) state <= state_bit(ADVANCE_INSTRUCTION);
                    else if (descriptor[0][8] && lane != last_lane) lane <= last_lane;
                    else case (opcode)
                        1: begin embedding_offset <= embedding_offsets[lane]; state <= state_bit(EMBED_ADDRESS); end
                        2: state <= state_bit(NORM_READ);
                        3,9: state <= state_bit(QUANT_MAX_READ);
                        4: state <= state_bit(ROPE_READ);
                        5: state <= state_bit(KV_ADDRESS);
                        6: begin max_value <= NEG_MAX; state <= state_bit(ATT_Q); end
                        7: state <= state_bit(ADD_READ);
                        8: state <= state_bit(SILU_READ);
                        10: begin next_position <= next_position+{8'b0,batch_count}; finish(0); end
                        default: finish(4);
                    endcase
                end

                state[EMBED_ADDRESS]: begin cursor <= address+embedding_offset; state <= state_bit(EMBED_SCALE); end
                state[EMBED_SCALE]: read_ext(cursor+4,EMBED_NEXT);
                state[EMBED_NEXT]: begin factor <= ext_word; read_ext(cursor+{19'b0,i[4:3]},EMBED_CONVERT); end
                state[EMBED_CONVERT]: calculate(I2F,{{28{embed_code[3]}},embed_code},0,EMBED_SCALE_VALUE);
                state[EMBED_SCALE_VALUE]: calculate(FMUL,fp_value,factor,EMBED_STORE);
                state[EMBED_STORE]: put_ram(destination+i,fp_value,EMBED_ADVANCE);
                state[EMBED_ADVANCE]: if (last_element) state <= state_bit(ADVANCE_POSITION);
                    else begin
                        i <= i+1'b1;
                        if (i[4:0] == 31) begin cursor <= cursor+5; state <= state_bit(EMBED_SCALE); end
                        else read_ext(cursor+{19'b0,next_coordinate[4:3]},EMBED_CONVERT);
                    end

                state[NORM_READ]: read_ram(source+group_offset+i,NORM_SQUARE);
                state[NORM_SQUARE]: calculate(FMUL,vector_word,vector_word,NORM_ACCUMULATE);
                state[NORM_ACCUMULATE]: calculate(FADD,accumulator,fp_value,NORM_NEXT);
                state[NORM_NEXT]: if (last_element) calculate(FDIV,fp_value,width == 32 ? 32'h42000000 : 32'h43000000,NORM_EPSILON);
                    else begin accumulator <= fp_value; i <= i+1'b1; state <= state_bit(NORM_READ); end
                state[NORM_EPSILON]: calculate(FADD,fp_value,configuration[3],NORM_SQRT);
                state[NORM_SQRT]: calculate(FSQRT,fp_value,0,NORM_INVERSE);
                state[NORM_INVERSE]: calculate(FDIV,ONE,fp_value,NORM_FACTOR);
                state[NORM_FACTOR]: begin factor <= fp_value; i <= 0; state <= state_bit(NORM_WEIGHT); end
                state[NORM_WEIGHT]: read_ext(address+{9'b0,i},NORM_VALUE);
                state[NORM_VALUE]: read_ram(source+group_offset+i,NORM_PRODUCT);
                state[NORM_PRODUCT]: calculate(FMUL,vector_word,factor,NORM_SCALE);
                state[NORM_SCALE]: calculate(FMUL,fp_value,ext_word,NORM_STORE);
                state[NORM_STORE]: put_ram(destination+group_offset+i,fp_value,NORM_ADVANCE);
                state[NORM_ADVANCE]: if (!last_element) begin i <= i+1'b1; state <= state_bit(NORM_WEIGHT); end
                    else if (last_row_group) state <= state_bit(ADVANCE_POSITION);
                    else begin
                        group_number <= group_number+1'b1; group_offset <= group_offset+width;
                        i <= 0; accumulator <= 0; state <= state_bit(NORM_READ);
                    end

                state[QUANT_MAX_READ]: read_ram(source+group_offset+i,QUANT_MAX_UPDATE);
                state[QUANT_MAX_UPDATE]: begin
                    magnitude_is_larger <= magnitude > max_value;
                    state <= state_bit(QUANT_MAX_COMMIT);
                end
                state[QUANT_MAX_COMMIT]: if (i == 31) calculate(FDIV,group_max,32'h42fe0000,QUANT_SCALE);
                    else begin max_value <= group_max; i <= i+1'b1; state <= state_bit(QUANT_MAX_READ); end
                state[QUANT_SCALE]: begin
                    factor <= fp_value;
                    act_scale[{lane,group_number[3:0]}] <= fp_value;
                    i <= 0; pack <= 0; state <= state_bit(QUANT_READ);
                end
                state[QUANT_READ]: read_ram(source+group_offset+i,QUANT_DIVIDE);
                state[QUANT_DIVIDE]: calculate(FDIV, factor == 0 ? 32'b0 : vector_word,
                                        factor == 0 ? ONE : factor, QUANT_PREPARE);
                state[QUANT_PREPARE]: begin
                    quant_mantissa <= {1'b1,fp_value[22:0]};
                    // For the in-range exponents, (149 - exponent) fits in
                    // five bits. Leave the first discarded bit for rounding.
                    quant_shift <= 5'd21 - fp_value[27:23];
                    quant_negative <= fp_value[31];
                    quant_zero <= fp_value[30:23] <= 8'd125;
                    quant_saturated <= fp_value[30:23] >= 8'd150;
                    state <= state_bit(QUANT_ALIGN);
                end
                state[QUANT_ALIGN]: begin
                    quant_aligned <= quant_mantissa >> quant_shift;
                    state <= state_bit(QUANT_STORE);
                end
                state[QUANT_STORE]: begin
                    pack <= pack_next;
                    if (i != 31) begin i <= i+1'b1; state <= state_bit(QUANT_READ); end
                    else if (!last_quant_group) begin
                        group_offset <= group_offset+12'd32; group_number <= group_number+1'b1;
                        i <= 0; max_value <= 0; state <= state_bit(QUANT_MAX_READ);
                    end else if (lane != last_lane) begin
                        lane <= lane+1'b1; i <= 0; group_number <= 0; group_offset <= 0;
                        max_value <= 0; state <= state_bit(QUANT_MAX_READ);
                    end else begin
                        lane <= opcode == 9 ? last_lane : 0;
                        group_number <= 0;
                        max_value <= NEG_MAX;
                        allowed_index <= 0;
                        state <= masked_head ? state_bit(ALLOWED_READ) : state_bit(MATRIX_WORD);
                    end
                end
                state[ALLOWED_READ]: read_ext(ALLOWED_ADDRESS+{17'b0,allowed_index[4:1]},ALLOWED_TOKEN);
                state[ALLOWED_TOKEN]: begin
                    if (allowed_token >= configuration[1][15:0]) finish(5);
                    else begin row <= allowed_token; state <= state_bit(ALLOWED_OFFSET); end
                end
                state[ALLOWED_OFFSET]: begin row_offset <= row*21'd20; state <= state_bit(ALLOWED_ROW); end
                state[ALLOWED_ROW]: begin cursor <= address+row_offset; group_number <= 0; state <= state_bit(MATRIX_WORD); end
                state[MATRIX_WORD]: begin
                    memory_address <= cursor;
                    matrix_words <= 0;
                    dot_groups <= 0;
                    state <= state_bit(MATRIX_STREAM);
                end
                state[MATRIX_STREAM]: begin
                    // Launch the next read as the previous word enters the DSP
                    // pipeline. The fifth word is the FP32 weight scale.
                    if (memory_complete) begin
                        memory_address <= memory_address + 1'b1;
                        matrix_words <= matrix_words + 1'b1;
                        if (matrix_words == 4) ext_word <= memory_result;
                    end
                    if (dot_ready) dot_groups <= dot_groups + 1'b1;
                    if (matrix_words == 5 && dot_groups == 4) state <= state_bit(MATRIX_CONVERT);
                end
                state[MATRIX_CONVERT]: calculate(I2F,{{15{integer_sum[lane][16]}},integer_sum[lane]},0,MATRIX_WEIGHT);
                state[MATRIX_WEIGHT]: calculate(FMUL,fp_value,ext_word,MATRIX_ACTIVATION);
                state[MATRIX_ACTIVATION]: calculate(FMUL,fp_value,act_scale[{lane,group_number[3:0]}],MATRIX_ACCUMULATE);
                state[MATRIX_ACCUMULATE]: calculate(FADD,group_number == 0 ? 32'b0 : matrix_accumulator[lane],
                                             fp_value,MATRIX_ADVANCE);
                state[MATRIX_ADVANCE]: begin
                    if (!last_group) begin
                        matrix_accumulator[lane] <= fp_value;
                        state <= state_bit(MATRIX_NEXT_LANE);
                    end else if (fp_value[30:23] == 255) finish(6);
                    else begin
                        if (opcode == 9) begin
                            candidate_key <= ordered(fp_value);
                            maximum_key <= ordered(max_value);
                            state <= state_bit(BEST_COMPARE);
                        end else put_ram(destination+row[11:0],fp_value,MATRIX_NEXT_LANE);
                    end
                end
                state[MATRIX_NEXT_LANE]: begin
                    if (lane == last_lane) begin
                        lane <= opcode == 9 ? last_lane : 0;
                        cursor <= cursor+21'd5;
                        if (last_group) state <= state_bit(MATRIX_NEXT_ROW);
                        else begin group_number <= group_number+1'b1; state <= state_bit(MATRIX_WORD); end
                    end else begin lane <= lane+1'b1; state <= state_bit(MATRIX_CONVERT); end
                end
                state[MATRIX_NEXT_ROW]: if (masked_head) begin
                        if (allowed_index+5'd1 == allowed_rows) state <= state_bit(ADVANCE_INSTRUCTION);
                        else begin allowed_index <= allowed_index+1'b1; state <= state_bit(ALLOWED_READ); end
                    end else if (last_row) state <= state_bit(ADVANCE_INSTRUCTION);
                    else begin row <= row+1'b1; group_number <= 0; state <= state_bit(MATRIX_WORD); end

                state[ROPE_READ]: read_pair(source+group_offset+i,source+group_offset+i+12'd16,ROPE_SAVE);
                state[ROPE_SAVE]: begin
                    left_value <= first_operand; right_value <= vector_word;
                    read_ext(rotary_cos,ROPE_COS);
                end
                state[ROPE_COS]: begin cosine <= ext_word; read_ext(memory_address+1'b1,ROPE_SIN); end
                state[ROPE_SIN]: begin sine <= ext_word; calculate(FMUL,left_value,cosine,ROPE_LC); end
                state[ROPE_LC]: begin accumulator <= fp_value; calculate(FMUL,right_value,sine,ROPE_RS); end
                state[ROPE_RS]: calculate(FSUB,accumulator,fp_value,ROPE_LEFT);
                state[ROPE_LEFT]: put_ram(destination+group_offset+i,fp_value,ROPE_RC);
                state[ROPE_RC]: calculate(FMUL,right_value,cosine,ROPE_LS);
                state[ROPE_LS]: begin accumulator <= fp_value; calculate(FMUL,left_value,sine,ROPE_RIGHT); end
                state[ROPE_RIGHT]: calculate(FADD,accumulator,fp_value,ROPE_STORE);
                state[ROPE_STORE]: put_ram(destination+group_offset+i+12'd16,fp_value,ROPE_NEXT);
                state[ROPE_NEXT]: if (i != 15) begin i <= i+1'b1; state <= state_bit(ROPE_READ); end
                    else if (last_row_group) state <= state_bit(ADVANCE_POSITION);
                    else begin group_number <= group_number+1'b1; group_offset <= group_offset+12'd32;
                               i <= 0; state <= state_bit(ROPE_READ); end

                state[KV_ADDRESS]: begin cursor <= address+{3'b0,position,7'b0}; state <= state_bit(KV_READ); end
                state[KV_READ]: read_ram(source+i,KV_WORD);
                state[KV_WORD]: write_ext(cursor+{9'b0,i},vector_word,KV_NEXT);
                state[KV_NEXT]: if (last_element) state <= state_bit(ADVANCE_POSITION);
                    else begin i <= i+1'b1; state <= state_bit(KV_READ); end

                state[ATT_Q]: read_ram(source_head,ATT_K);
                state[ATT_K]: read_ext(attention_key,ATT_PRODUCT);
                state[ATT_PREFETCH]: if (prefetch_ready) begin
                    ext_word <= prefetched_word;
                    prefetch_ready <= 0;
                    state <= state_bit(ATT_PRODUCT);
                end
                state[ATT_PRODUCT]: begin
                    prefetch_next_attention_word();
                    // The next query coordinate can come out of SRAM while
                    // the current product is multiplied and accumulated.
                    if (i != 31) ram_address <= ram_address + 1'b1;
                    calculate(FMUL,vector_word,ext_word,ATT_ACCUMULATE);
                end
                state[ATT_ACCUMULATE]: if (add_ready) begin
                    if (i == 31) state <= state_bit(ATT_NEXT);
                    else begin i <= i+1'b1; state <= state_bit(ATT_PREFETCH); end
                end
                state[ATT_NEXT]: if (attention_add_complete) calculate(FMUL,attention_sum,INV_SQRT_32,ATT_SCORE);
                state[ATT_SCORE]: begin
                    candidate_key <= ordered(fp_value);
                    maximum_key <= ordered(max_value);
                    state <= state_bit(BEST_COMPARE);
                end
                state[BEST_COMPARE]: begin
                    candidate_is_larger <= candidate_key > maximum_key;
                    state <= state_bit(BEST_COMMIT);
                end
                state[BEST_COMMIT]: begin
                    if (candidate_is_larger) begin
                        max_value <= fp_value;
                        if (opcode == 9) best_token <= row;
                    end
                    if (opcode == 9) state <= state_bit(MATRIX_NEXT_LANE);
                    else put_ram(SCORES+{1'b0,time_index},fp_value,ATT_SCORE_NEXT);
                end
                state[ATT_SCORE_NEXT]: begin
                    i <= 0; accumulator <= 0;
                    if (time_index == position) begin time_index <= 0; state <= state_bit(SOFTMAX_READ); end
                    else begin time_index <= time_index+1'b1; state <= state_bit(ATT_Q); end
                end
                state[SOFTMAX_READ]: read_ram(SCORES+{1'b0,time_index},SOFTMAX_SUB);
                state[SOFTMAX_SUB]: calculate(FSUB,score_word,max_value,SOFTMAX_EXP);
                state[SOFTMAX_EXP]: calculate(FEXP,fp_value,0,SOFTMAX_STORE);
                state[SOFTMAX_STORE]: put_ram(SCORES+{1'b0,time_index},fp_value,SOFTMAX_ACCUMULATE);
                state[SOFTMAX_ACCUMULATE]: calculate(FADD,accumulator,fp_value,SOFTMAX_NEXT);
                state[SOFTMAX_NEXT]: begin
                    accumulator <= fp_value;
                    if (time_index == position) begin time_index <= 0; state <= state_bit(VALUE_SCORE); end
                    else begin time_index <= time_index+1'b1; state <= state_bit(SOFTMAX_READ); end
                end
                state[VALUE_SCORE]: read_ram(SCORES+{1'b0,time_index},VALUE_WEIGHT);
                state[VALUE_WEIGHT]: calculate(FDIV,score_word,accumulator,VALUE_START);
                state[VALUE_START]: begin
                    factor <= fp_value;
                    memory_address <= attention_value;
                    value_fetched <= 0; value_product_index <= 0; value_store_index <= 0;
                    state <= state_bit(VALUE_STREAM);
                end
                state[VALUE_STREAM]: if (value_retire && value_store_index == 31) begin
                    if (time_index != position) begin time_index <= time_index+1'b1; state <= state_bit(VALUE_SCORE); end
                    else begin i <= 0; state <= state_bit(VALUE_RESULT_READ); end
                end
                state[VALUE_RESULT_READ]: state <= state_bit(VALUE_RESULT_WAIT);
                state[VALUE_RESULT_WAIT]: state <= state_bit(VALUE_STORE);
                state[VALUE_STORE]: put_ram(output_coordinate,value_word,VALUE_RESULT_NEXT);
                state[VALUE_RESULT_NEXT]: if (i != 31) begin i <= i+1'b1; state <= state_bit(VALUE_RESULT_READ); end
                    else if (head == 3) state <= state_bit(ADVANCE_POSITION);
                    else begin head <= head+1'b1; time_index <= 0; i <= 0; accumulator <= 0;
                               max_value <= NEG_MAX; state <= state_bit(ATT_Q); end

                state[ADD_READ]: read_pair(destination+i,source+i,ADD_RESULT);
                state[ADD_RESULT]: calculate(FADD,first_operand,vector_word,ADD_WRITE);
                state[ADD_WRITE]: put_ram(destination+i,fp_value,ADD_NEXT);
                state[ADD_NEXT]: if (last_element) state <= state_bit(ADVANCE_POSITION);
                    else begin i <= i+1'b1; state <= opcode == 7 ? state_bit(ADD_READ) : state_bit(SILU_READ); end
                state[SILU_READ]: read_pair(destination+i,source+i,SILU_EXP);
                state[SILU_EXP]: calculate(FEXP,first_operand ^ 32'h80000000,0,SILU_ADD);
                state[SILU_ADD]: calculate(FADD,ONE,fp_value,SILU_DIVIDE);
                state[SILU_DIVIDE]: calculate(FDIV,first_operand,fp_value,SILU_PRODUCT);
                state[SILU_PRODUCT]: calculate(FMUL,fp_value,vector_word,SILU_STORE);
                state[SILU_STORE]: put_ram(destination+i,fp_value,ADD_NEXT);
                default: finish(4);
            endcase
        end
    end
endmodule
