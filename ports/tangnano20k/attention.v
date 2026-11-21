// Attention for one KV head and its two query heads, at one or two consecutive
// query positions. Every accumulation follows the scalar implementation's
// order. Scores, exponents and normalized probabilities share the same RAM.
module tang_attention (
    input wire clk, resetn, start,
    input wire [20:0] key_base,
    input wire [9:0] first_position,
    input wire pair,
    input wire query_write,
    input wire [6:0] query_index,
    input wire [31:0] query_data,
    input wire result_read,
    input wire [6:0] result_index,
    output wire [31:0] result,
    output reg done,

    output wire memory_request, memory_burst,
    output wire [20:0] memory_address,
    input wire memory_complete,
    input wire [31:0] memory_data,

    output wire scalar_start,
    output reg [2:0] scalar_operation,
    output reg [31:0] scalar_a, scalar_b,
    input wire scalar_complete,
    input wire [31:0] scalar_value,

    output reg mul_start,
    output wire [31:0] mul_a,
    output reg [31:0] mul_b,
    input wire mul_complete,
    input wire [31:0] mul_value,
    output reg add_start,
    output wire [31:0] add_a,
    output reg [31:0] add_b,
    input wire add_complete,
    input wire [31:0] add_value
);
    localparam IDLE=0, KEY_WAIT=1, KEY_DOT=2, KEY_DRAIN=3, SCORE_SCALE=4, SCORE_DRAIN=5,
               SOFT_READ=6, SOFT_SUB=7, SOFT_EXP=8, SOFT_ADD=9, SOFT_ADVANCE=10,
               PROB_READ=11, PROB_DIVIDE=12, PROB_STORE=13, SCALAR_WAIT=14,
               VALUE_WAIT=15, VALUE_PROB_READ=16, VALUE_PROB_SAVE=17, VALUE_DOT=18, VALUE_DRAIN=19;
    localparam FADD=0, FSUB=1, FDIV=3, FEXP=6;
    localparam [31:0] INV_SQRT_32=32'h3e3504f3, NEG_MAX=32'hff7fffff;

    reg [4:0] state, continuation;
    reg [1:0] stream;
    reg [2:0] key;
    reg [4:0] coordinate;
    reg [9:0] tile_start, time_index;
    reg [4:0] drain;
    reg read_bank, load_bank, loading, tile_ready, load_values;
    reg [13:0] load_row;
    reg [2:0] load_key, load_last;
    reg [4:0] load_coordinate;
    reg [31:0] maxima [0:3];
    reg [31:0] probabilities [0:3];
    reg [31:0] denominator;
    wire [1:0] final_stream = pair ? 2'd3 : 2'd1;
    wire [9:0] last_position = first_position + {9'b0,pair};
    wire [9:0] stream_end = first_position + {9'b0,stream[1]};
    wire [9:0] tile_position = tile_start | {7'b0,key};
    wire final_tile = tile_start[9:3] == last_position[9:3];
    wire position_valid = tile_position <= stream_end;

    wire dot_pass = state == KEY_DOT || state == KEY_DRAIN;
    wire score_pass = state == SCORE_SCALE || state == SCORE_DRAIN;
    wire value_pass = state == VALUE_DOT || state == VALUE_PROB_READ ||
                      state == VALUE_PROB_SAVE || state == VALUE_DRAIN;

    (* ram_style="block" *) reg [31:0] queries [0:127];
    (* ram_style="block" *) reg [31:0] kv_tile [0:511];
    (* ram_style="block" *) reg [31:0] scores [0:4095];
    (* ram_style="block" *) reg [31:0] accumulators [0:127];
    reg [31:0] source_score, accumulated;
    assign result = accumulated;
    assign memory_request = loading;
    assign memory_burst = loading && load_coordinate[2:0] == 0;
    assign memory_address = {load_row,load_values,key_base[5],load_coordinate};

    wire issue_key = state == KEY_DOT && position_valid;
    wire issue_scale = state == SCORE_SCALE && position_valid;
    wire issue_value = state == VALUE_DOT && position_valid;
    wire issue_product = issue_key || issue_scale || issue_value;
    wire first_add = issue_key ? coordinate == 0 : tile_position == 0;
    wire [6:0] dot_index = {2'b0,key,stream};
    wire [6:0] value_index = {stream,coordinate};
    wire [6:0] issue_index = issue_value ? value_index : dot_index;
    reg [6:0] product_index;
    reg product_first;
    reg [31:0] query_operand, probability_operand;
    reg value_operand, scale_operand;
    // The shared streaming multiplier has eight stages. The model's adder
    // has eight stages plus the input register in tang_fp32.
    reg [7:0] mul_tags [0:7];
    reg [6:0] add_tags [0:8];
    reg [6:0] add_index;
    reg add_first;
    wire read_accum = (dot_pass || value_pass) && mul_complete;
    wire [6:0] read_accum_index = read_accum ? mul_tags[7][6:0] : issue_scale ? dot_index : result_index;
    wire [11:0] scale_index = {mul_tags[7][1:0],tile_start[9:3],mul_tags[7][4:2]};
    wire [11:0] soft_index = {stream,time_index};
    wire [11:0] value_probability_index = {stream,tile_position};
    wire score_read = state == SOFT_READ || state == PROB_READ || state == VALUE_PROB_READ;
    wire [11:0] score_read_index = state == VALUE_PROB_READ ? value_probability_index : soft_index;

    // Convert IEEE-754 magnitude ordering to an unsigned comparison, treating
    // both signs of zero as equal. This is the same comparison as the sequencer.
    function [31:0] ordered;
        input [31:0] value;
        ordered = value[30:0] == 0 ? 32'h80000000 : value[31] ? ~value : value ^ 32'h80000000;
    endfunction
    reg compare_score;
    reg [1:0] compare_stream;
    reg [31:0] compare_value, compare_key;
    reg commit_score;
    reg [1:0] commit_stream;
    reg [31:0] commit_value, commit_key;
    reg [31:0] maximum_key [0:3];

    wire store_exp = state == SOFT_ADD;
    wire store_prob = state == PROB_STORE;
    wire store_score = score_pass && mul_complete;
    wire [11:0] score_write_index = store_score ? scale_index : soft_index;
    assign add_a = add_first ? 32'b0 : accumulated;
    integer p;
    always @(posedge clk) begin
        if (query_write) queries[query_index] <= query_data;
        if (loading && memory_complete) kv_tile[{load_bank,load_key,load_coordinate}] <= memory_data;
        if (score_read) source_score <= scores[score_read_index];
        if (store_score || store_exp || store_prob)
            scores[score_write_index] <= store_score ? mul_value : scalar_value;

        if (read_accum || issue_scale || result_read)
            accumulated <= accumulators[read_accum_index];
        if ((dot_pass || value_pass) && add_complete)
            accumulators[add_tags[8]] <= add_value;

        mul_start <= resetn && issue_product;
        if (issue_product) begin
            product_index <= issue_index;
            product_first <= first_add;
        end
        if (issue_key)
            query_operand <= queries[value_index];
        if (issue_value)
            probability_operand <= probabilities[stream];
        if (issue_key || issue_value)
            mul_b <= kv_tile[{read_bank,key,coordinate}];
        if (issue_scale) mul_b <= INV_SQRT_32;
        value_operand <= issue_value;
        scale_operand <= issue_scale;

        mul_tags[0] <= {product_first,product_index};
        for (p=1; p<8; p=p+1) mul_tags[p] <= mul_tags[p-1];
        add_start <= resetn && read_accum;
        if (read_accum) begin
            add_first <= mul_tags[7][7];
            add_index <= mul_tags[7][6:0];
            add_b <= mul_value;
        end
        add_tags[0] <= add_index;
        // add_start and add_b are the registered product. Carry the same tag.
        for (p=1; p<9; p=p+1) add_tags[p] <= add_tags[p-1];

        compare_score <= resetn && store_score;
        if (store_score) begin
            compare_stream <= mul_tags[7][1:0];
            compare_value <= mul_value;
            compare_key <= ordered(mul_value);
        end
        commit_score <= resetn && compare_score;
        if (compare_score) begin
            commit_stream <= compare_stream;
            commit_value <= compare_value;
            commit_key <= compare_key;
        end
    end
    genvar h;
    generate for (h=0; h<4; h=h+1) begin: reduce_max
        reg high_greater, high_equal, low_greater;
        always @(posedge clk) begin
            high_greater <= compare_key[31:16] > maximum_key[h][31:16];
            high_equal <= compare_key[31:16] == maximum_key[h][31:16];
            low_greater <= compare_key[15:0] > maximum_key[h][15:0];
            if (state == IDLE && start) begin
                maxima[h] <= NEG_MAX;
                maximum_key[h] <= ordered(NEG_MAX);
            end else if (commit_score && commit_stream == h &&
                         (high_greater || (high_equal && low_greater))) begin
                maxima[h] <= commit_value;
                maximum_key[h] <= commit_key;
            end
        end
    end endgenerate

    // On a scale issue, the RAM output itself is the first multiplier input.
    // Otherwise use the registered Q coordinate or normalized probability.
    assign mul_a = scale_operand ? accumulated : value_operand ? probability_operand : query_operand;

    assign scalar_start = state == SOFT_SUB || state == SOFT_EXP ||
                          state == SOFT_ADD || state == PROB_DIVIDE;
    always @* begin
        scalar_operation = FSUB;
        scalar_a = source_score;
        scalar_b = maxima[stream];
        case (state)
            SOFT_EXP: begin scalar_operation = FEXP; scalar_a = scalar_value; scalar_b = 0; end
            SOFT_ADD: begin scalar_operation = FADD; scalar_a = denominator; scalar_b = scalar_value; end
            PROB_DIVIDE: begin scalar_operation = FDIV; scalar_b = denominator; end
            default: begin end
        endcase
    end

    task load_tile;
        input [9:0] first_key;
        input for_value, bank;
        begin
            load_row <= key_base[20:7] + {4'b0,first_key};
            load_bank <= bank;
            load_values <= for_value;
            load_key <= 0;
            load_coordinate <= 0;
            load_last <= first_key[9:3] == last_position[9:3] ? last_position[2:0] : 3'd7;
            loading <= 1;
            tile_ready <= 0;
        end
    endtask

    task begin_pass;
        input for_value;
        begin
            load_tile(0,for_value,0);
            tile_start <= 0;
            read_bank <= 0;
            state <= for_value ? VALUE_WAIT : KEY_WAIT;
        end
    endtask

    task wait_scalar;
        input [4:0] next_state;
        begin
            continuation <= next_state;
            state <= SCALAR_WAIT;
        end
    endtask

    always @(posedge clk) begin
        done <= 0;
        if (!resetn) begin
            state <= IDLE;
            loading <= 0;
            tile_ready <= 0;
        end else begin
            if (loading && memory_complete) begin
                load_coordinate <= load_coordinate + 1'b1;
                if (load_coordinate == 31) begin
                    load_row <= load_row + 1'b1;
                    load_key <= load_key + 1'b1;
                    if (load_key == load_last) begin
                        loading <= 0;
                        tile_ready <= 1;
                    end
                end
            end
            case (state)
            IDLE: if (start) begin_pass(0);
            KEY_WAIT, VALUE_WAIT: if (tile_ready) begin
                key <= 0;
                coordinate <= 0;
                stream <= 0;
                state <= state == KEY_WAIT ? KEY_DOT : VALUE_PROB_READ;
                if (!final_tile) load_tile(tile_start + 10'd8,state == VALUE_WAIT,!read_bank);
            end
            KEY_DOT: begin
                if (stream == final_stream) begin
                    stream <= 0;
                    if (key == 7) begin
                        key <= 0;
                        if (coordinate == 31) begin
                            drain <= 0;
                            state <= KEY_DRAIN;
                        end else coordinate <= coordinate + 1'b1;
                    end else key <= key + 1'b1;
                end else stream <= stream + 1'b1;
            end
            KEY_DRAIN: begin
                drain <= drain + 1'b1;
                if (drain == 20) state <= SCORE_SCALE;
            end
            SCORE_SCALE: begin
                if (stream == final_stream) begin
                    stream <= 0;
                    if (key == 7) begin
                        drain <= 0;
                        state <= SCORE_DRAIN;
                    end else key <= key + 1'b1;
                end else stream <= stream + 1'b1;
            end
            SCORE_DRAIN: begin
                drain <= drain + 1'b1;
                if (drain == 11) begin
                    if (!final_tile) begin
                        tile_start <= tile_start + 10'd8;
                        read_bank <= !read_bank;
                        state <= KEY_WAIT;
                    end
                    else begin
                        time_index <= 0;
                        denominator <= 0;
                        state <= SOFT_READ;
                    end
                end
            end
            SOFT_READ: state <= SOFT_SUB;
            SOFT_SUB: wait_scalar(SOFT_EXP);
            SOFT_EXP: wait_scalar(SOFT_ADD);
            SOFT_ADD: wait_scalar(SOFT_ADVANCE);
            SOFT_ADVANCE: begin
                denominator <= scalar_value;
                if (time_index == stream_end) begin
                    time_index <= 0;
                    state <= PROB_READ;
                end else begin
                    time_index <= time_index + 1'b1;
                    state <= SOFT_READ;
                end
            end
            PROB_READ: state <= PROB_DIVIDE;
            PROB_DIVIDE: wait_scalar(PROB_STORE);
            PROB_STORE: begin
                if (time_index != stream_end) begin
                    time_index <= time_index + 1'b1;
                    state <= PROB_READ;
                end else if (stream != final_stream) begin
                    stream <= stream + 1'b1;
                    time_index <= 0;
                    denominator <= 0;
                    state <= SOFT_READ;
                end else begin_pass(1);
            end
            SCALAR_WAIT: if (scalar_complete) state <= continuation;
            VALUE_PROB_READ: state <= VALUE_PROB_SAVE;
            VALUE_PROB_SAVE: begin
                probabilities[stream] <= source_score;
                if (stream == final_stream) begin
                    stream <= 0;
                    state <= VALUE_DOT;
                end else begin
                    stream <= stream + 1'b1;
                    state <= VALUE_PROB_READ;
                end
            end
            VALUE_DOT: begin
                if (stream == final_stream) begin
                    stream <= 0;
                    if (coordinate != 31) coordinate <= coordinate + 1'b1;
                    else if (key == 7 || tile_position == last_position) begin
                        drain <= 0;
                        state <= VALUE_DRAIN;
                    end else begin
                        coordinate <= 0;
                        key <= key + 1'b1;
                        state <= VALUE_PROB_READ;
                    end
                end else stream <= stream + 1'b1;
            end
            VALUE_DRAIN: begin
                drain <= drain + 1'b1;
                if (drain == 20) begin
                    if (!final_tile) begin
                        tile_start <= tile_start + 10'd8;
                        read_bank <= !read_bank;
                        state <= VALUE_WAIT;
                    end
                    else begin
                        done <= 1;
                        state <= IDLE;
                    end
                end
            end
            default: state <= IDLE;
            endcase
        end
    end
endmodule
