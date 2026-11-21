// CRC32-protected board link. Words are little endian. One request at a time.
module tang_link_control #(
    parameter CLOCK_HZ = 54000000,
    parameter BUILD_ID = 32'h54323031,
    parameter MODEL_ENABLED = 0,
    parameter PREFILL_LANES = 4
) (
    input wire clk, resetn,
    input wire [7:0] host_input, pico_input,
    input wire host_available, pico_available, host_tx_busy, pico_tx_busy,
    output wire host_pop, pico_pop, host_push, pico_push,
    output reg [7:0] serial_output,
    output wire memory_request, memory_write,
    output reg [20:0] memory_address,
    output reg [31:0] memory_data,
    input wire memory_complete,
    input wire [31:0] memory_result,
    output wire dot_valid,
    output wire [31:0] dot_weights,
    output wire [63:0] dot_activations,
    input wire dot_ready,
    input wire signed [14:0] dot_result,
    output reg model_start, model_reset,
    output wire [PREFILL_LANES*16-1:0] model_tokens,
    output wire [2:0] model_count,
    output wire model_output,
    output wire [4:0] model_allowed,
    output wire [10:0] model_seek,
    input wire model_done,
    input wire [7:0] model_status,
    input wire [31:0] model_result, model_checksum, model_cycles,
    input wire [PREFILL_LANES*32-1:0] model_checksums
);
    localparam SEEK = 0, SYNC = 1, HEADER = 2, PAYLOAD = 3, CHECKSUM = 4,
        COMMAND = 5, LOAD_WORD = 6, WRITE_WORD = 7, READ_WORD = 8, CHECK_RANGE = 9,
        START_DOT = 10, WAIT_DOT = 11, TURN = 12, SEND = 13, START_MODEL = 14,
        WAIT_MODEL = 15, RESET_MODEL = 16, CHECK_RANGE_HIGH = 17, CHECK_RANGE_DONE = 18,
        DISPATCH = 19, PREPARE_REPLY = 20, PREPARE_BYTE = 21, WAIT_SEEK = 22;
    localparam [7:0] OK = 0, BAD_CRC = 1, BAD_RANGE = 2, BAD_COMMAND = 3;
    localparam [7:0] FORWARD = 6, RESET = 7, PREFILL = 8, SEEK_CONTEXT = 9, FEATURES = 10;
    reg [4:0] state;
    reg selected_pico;
    reg [3:0] header_index;
    reg [9:0] payload_index;
    reg [7:0] command_code, request_id, status;
    reg [31:0] address, receive_crc, transmit_crc, memory_crc;
    reg [15:0] length;
    reg [1:0] checksum_index;
    reg [23:0] checksum_low;
    reg [31:0] payload_first [0:2];
    (* ram_style = "block" *) reg [31:0] payload_ram [0:255];
    reg [23:0] assembled_word;
    reg [7:0] word_index;
    reg [21:0] range_words;
    reg [15:0] range_high;
    reg [5:0] outgoing_index, reply_bytes, crc_index;
    reg [15:0] turnaround;
    reg [7:0] reply_byte;
    reg byte_in_crc, last_reply_byte;
    reg [31:0] result0, result1, result2;
    reg [23:0] write_end, range_end;
    reg write_shape, read_shape, range_shape, dot_shape, empty_payload, forward_shape, prefill_shape, seek_shape;
    localparam NO_BYTE_LIMIT = CLOCK_HZ / 10;
    reg [23:0] no_byte_ticks;
    reg byte_ready, received_pico;
    reg [7:0] byte_in;

    wire receiving = state <= CHECKSUM;
    wire use_pico = state == SEEK ? !host_available && pico_available : selected_pico;
    wire accept_byte = resetn && receiving && !byte_ready && (use_pico ? pico_available : host_available);
    wire tx_valid = state == SEND && !(selected_pico ? pico_tx_busy : host_tx_busy);
    assign host_pop = accept_byte && !use_pico;
    assign pico_pop = accept_byte && use_pico;
    always @(posedge clk) begin
        byte_ready <= accept_byte;
        if (accept_byte) begin
            byte_in <= use_pico ? pico_input : host_input;
            received_pico <= use_pico;
        end
    end
    assign host_push = tx_valid && !selected_pico;
    assign pico_push = tx_valid && selected_pico;
    assign dot_valid = state == START_DOT;
    assign dot_weights = payload_first[0];
    assign dot_activations = {payload_first[2], payload_first[1]};
    assign memory_request = state == WRITE_WORD || state == READ_WORD || state == CHECK_RANGE;
    assign memory_write = state == WRITE_WORD;
    assign model_tokens = command_code == PREFILL ? {payload_first[2],payload_first[1],payload_first[0]} :
                                                   {{(PREFILL_LANES*16-16){1'b0}},address[15:0]};
    assign model_count = command_code == PREFILL ? length[3:1] : 3'd1;
    assign model_output = command_code == PREFILL ? address[0] : address[16];
    assign model_allowed = command_code == FORWARD ? address[21:17] : 5'd0;
    assign model_seek = command_code == SEEK_CONTEXT ? address[10:0] : 11'd0;
    wire [31:0] crc_out = ~transmit_crc;
    wire [5:0] reply_size = command_code == PREFILL && status == OK ?
                            6'd9 + {1'b0,model_count,2'b0} : 6'd13;
    wire [5:0] crc_offset = outgoing_index - crc_index;
    wire [5:0] batch_offset = outgoing_index - 6'd23;

    function [31:0] crc_byte;
        input [31:0] previous;
        input [7:0] value;
        reg [31:0] current;
        integer i;
        begin
            current = previous ^ {24'b0, value};
            for (i = 0; i < 8; i = i + 1)
                current = (current >> 1) ^ (current[0] ? 32'hedb88320 : 32'b0);
            crc_byte = current;
        end
    endfunction

    wire [15:0] crc_halfword = state == CHECK_RANGE_HIGH ? range_high : memory_result[15:0];
    wire [31:0] range_crc = crc_byte(crc_byte(memory_crc, crc_halfword[7:0]), crc_halfword[15:8]);
    wire aligned_address = !address[1:0] && address < 32'h800000;

    task respond;
        input [7:0] error;
        begin
            status <= error;
            state <= PREPARE_REPLY;
        end
    endtask

    always @* begin
        case (outgoing_index)
            0: reply_byte = 8'h5a;
            1: reply_byte = 8'ha5;
            2: reply_byte = command_code | 8'h80;
            3: reply_byte = request_id;
            4: reply_byte = {2'b0,reply_bytes};
            10: reply_byte = status;
            11,12,13,14: reply_byte = result0[8*(outgoing_index-11) +: 8];
            15,16,17,18: reply_byte = result1[8*(outgoing_index-15) +: 8];
            19,20,21,22: reply_byte = result2[8*(outgoing_index-19) +: 8];
            default: begin
                if (outgoing_index >= crc_index) reply_byte = crc_out[8*crc_offset[1:0] +: 8];
                else if (outgoing_index >= 23) reply_byte = model_checksums[8*batch_offset[4:0] +: 8];
                else reply_byte = 0;
            end
        endcase
    end

    always @(posedge clk) begin
        model_start <= 0;
        model_reset <= 0;
        if (!resetn) begin
            state <= SEEK;
            no_byte_ticks <= 0;
        end else if (state != SEEK && receiving && !byte_ready && no_byte_ticks == NO_BYTE_LIMIT) begin
            state <= SEEK;
        end else begin
            if (byte_ready || state == SEEK || !receiving) no_byte_ticks <= 0;
            else no_byte_ticks <= no_byte_ticks + 1'b1;
            case (state)
                SEEK: if (byte_ready && byte_in == 8'ha5) begin
                    selected_pico <= received_pico;
                    state <= SYNC;
                end
                SYNC: if (byte_ready) begin
                    if (byte_in == 8'h5a) begin
                        state <= HEADER;
                        header_index <= 0;
                        receive_crc <= 32'hffffffff;
                    end else if (byte_in != 8'ha5) state <= SEEK;
                end
                HEADER: if (byte_ready) begin
                    receive_crc <= crc_byte(receive_crc, byte_in);
                    header_index <= header_index + 1'b1;
                    case (header_index)
                        0: command_code <= byte_in;
                        1: request_id <= byte_in;
                        2: length[7:0] <= byte_in;
                        3: length[15:8] <= byte_in;
                        4,5,6,7: address[8*(header_index-4) +: 8] <= byte_in;
                    endcase
                    if (header_index == 7) begin
                        payload_index <= 0;
                        checksum_index <= 0;
                        state <= length == 0 ? CHECKSUM : length > 1024 ? SEEK : PAYLOAD;
                    end
                end
                PAYLOAD: if (byte_ready) begin
                    receive_crc <= crc_byte(receive_crc, byte_in);
                    if (payload_index < 12)
                        payload_first[payload_index[3:2]][8*payload_index[1:0] +: 8] <= byte_in;
                    if ({6'b0,payload_index} == length - 1'b1) state <= CHECKSUM;
                    else payload_index <= payload_index + 1'b1;
                end
                CHECKSUM: if (byte_ready) begin
                    if (checksum_index == 3) begin
                        if ({byte_in, checksum_low} == ~receive_crc) state <= COMMAND;
                        else respond(BAD_CRC);
                    end else begin
                        checksum_low[8*checksum_index +: 8] <= byte_in;
                        checksum_index <= checksum_index + 1'b1;
                    end
                end
                COMMAND: begin
                    memory_address <= address[22:2];
                    word_index <= 0;
                    write_end <= {1'b0,address[22:0]} + {8'b0,length};
                    range_end <= {1'b0,address[22:0]} + payload_first[0][23:0];
                    write_shape <= length != 0 && !length[1:0] && aligned_address;
                    read_shape <= !length && aligned_address;
                    range_shape <= length == 4 && payload_first[0] != 0 && !payload_first[0][1:0] &&
                                   payload_first[0] <= 32'h800000 && aligned_address;
                    dot_shape <= length == 12;
                    empty_payload <= !length;
                    forward_shape <= !length && address[31:22] == 0 &&
                                     (address[21:17] == 0 || (address[16] && address[21:17] <= 5'd24));
                    prefill_shape <= length >= 2 && length <= PREFILL_LANES*2 &&
                                     !length[0] && address[31:1] == 0;
                    seek_shape <= !length && address <= 1024;
                    state <= DISPATCH;
                end
                DISPATCH: begin
                    case (command_code)
                        1: if (write_shape && write_end <= 24'h800000) state <= LOAD_WORD;
                           else respond(BAD_RANGE);
                        2: if (read_shape) state <= READ_WORD; else respond(BAD_RANGE);
                        3: if (range_shape && range_end <= 24'h800000) begin
                               memory_crc <= 32'hffffffff;
                               range_words <= payload_first[0][23:2];
                               state <= CHECK_RANGE;
                           end else respond(BAD_RANGE);
                        4: if (dot_shape) state <= START_DOT; else respond(BAD_RANGE);
                        5: respond(empty_payload ? OK : BAD_RANGE);
                        FORWARD: if (forward_shape) state <= START_MODEL; else respond(BAD_RANGE);
                        RESET: if (empty_payload) state <= RESET_MODEL; else respond(BAD_RANGE);
                        PREFILL: if (prefill_shape) state <= START_MODEL; else respond(BAD_RANGE);
                        SEEK_CONTEXT: if (seek_shape) state <= RESET_MODEL; else respond(BAD_RANGE);
                        FEATURES: if (empty_payload && MODEL_ENABLED) respond(OK); else respond(BAD_COMMAND);
                        default: respond(BAD_COMMAND);
                    endcase
                end
                LOAD_WORD: state <= WRITE_WORD;
                WRITE_WORD: if (memory_complete) begin
                    if ({8'b0,word_index} == (length >> 2) - 1'b1) respond(OK);
                    else begin
                        word_index <= word_index + 1'b1;
                        memory_address <= memory_address + 1'b1;
                        state <= LOAD_WORD;
                    end
                end
                READ_WORD: if (memory_complete) respond(OK);
                CHECK_RANGE: if (memory_complete) begin
                    memory_crc <= range_crc;
                    range_high <= memory_result[31:16];
                    state <= CHECK_RANGE_HIGH;
                end
                CHECK_RANGE_HIGH: begin
                    memory_crc <= range_crc;
                    if (range_words == 1) state <= CHECK_RANGE_DONE;
                    else begin
                        range_words <= range_words - 1'b1;
                        memory_address <= memory_address + 1'b1;
                        state <= CHECK_RANGE;
                    end
                end
                CHECK_RANGE_DONE: respond(OK);
                START_DOT: state <= WAIT_DOT;
                WAIT_DOT: if (dot_ready) respond(OK);
                START_MODEL: begin model_start <= 1; state <= WAIT_MODEL; end
                WAIT_MODEL: if (model_done) respond(model_status);
                RESET_MODEL: begin model_reset <= 1; state <= WAIT_SEEK; end
                WAIT_SEEK: respond(OK);
                PREPARE_REPLY: begin
                    result0 <= 0;
                    result1 <= 0;
                    result2 <= 0;
                    if (status == OK) case (command_code)
                        1: result0 <= {16'b0,length};
                        2: result0 <= memory_result;
                        3: result0 <= ~memory_crc;
                        4: result0 <= {{17{dot_result[14]}},dot_result};
                        5: begin result0 <= BUILD_ID; result1 <= CLOCK_HZ; result2 <= 8388608; end
                        FEATURES: begin result0 <= 32'h314b544d; result1 <= PREFILL_LANES; result2 <= 24; end
                        SEEK_CONTEXT: result0 <= {16'b0,model_result[31:16]};
                        FORWARD, PREFILL: begin
                            result0 <= model_result; result1 <= model_checksum; result2 <= model_cycles;
                        end
                    endcase
                    reply_bytes <= reply_size;
                    crc_index <= 6'd10 + reply_size;
                    turnaround <= (CLOCK_HZ / 1000000) * 24;
                    transmit_crc <= 32'hffffffff;
                    outgoing_index <= 0;
                    state <= TURN;
                end
                TURN: begin
                    turnaround <= turnaround - 1'b1;
                    if (turnaround == 1) state <= PREPARE_BYTE;
                end
                PREPARE_BYTE: begin
                    serial_output <= reply_byte;
                    byte_in_crc <= outgoing_index >= 2 && outgoing_index < crc_index;
                    last_reply_byte <= outgoing_index == crc_index + 6'd3;
                    state <= SEND;
                end
                SEND: if (tx_valid) begin
                    if (byte_in_crc) transmit_crc <= crc_byte(transmit_crc, serial_output);
                    outgoing_index <= outgoing_index + 1'b1;
                    state <= last_reply_byte ? SEEK : PREPARE_BYTE;
                end
                default: state <= SEEK;
            endcase
        end
    end

    always @(posedge clk) begin
        if (state == PAYLOAD && byte_ready) begin
            assembled_word <= {byte_in, assembled_word[23:8]};
            if (payload_index[1:0] == 3)
                payload_ram[payload_index[9:2]] <= {byte_in, assembled_word};
        end
        if (state == LOAD_WORD) memory_data <= payload_ram[word_index];
    end
endmodule
