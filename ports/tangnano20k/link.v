// CRC32-protected board link. Words are little endian. One request at a time.
module tang_link_control #(
    parameter CLOCK_HZ = 54000000,
    parameter BUILD_ID = 32'h54323031
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
    output wire model_start, model_reset,
    output wire [15:0] model_token,
    output wire model_output,
    input wire model_done,
    input wire [7:0] model_status,
    input wire [31:0] model_result, model_checksum, model_cycles
);
    localparam SEEK = 0, SYNC = 1, HEADER = 2, PAYLOAD = 3, CHECKSUM = 4,
        COMMAND = 5, LOAD_WORD = 6, WRITE_WORD = 7, READ_WORD = 8, CHECK_RANGE = 9,
        START_DOT = 10, WAIT_DOT = 11, TURN = 12, SEND = 13, START_MODEL = 14,
        WAIT_MODEL = 15, RESET_MODEL = 16;
    localparam [7:0] OK = 0, BAD_CRC = 1, BAD_RANGE = 2, BAD_COMMAND = 3;
    reg [4:0] state;
    reg selected_pico;
    reg [3:0] header_index;
    reg [9:0] payload_index;
    reg [7:0] command_code, request_id, status;
    reg [31:0] address, checksum;
    reg [15:0] length;
    reg [1:0] checksum_index;
    reg [23:0] checksum_low;
    reg [31:0] payload_first [0:2];
    (* ram_style = "block" *) reg [31:0] payload_ram [0:255];
    reg [23:0] assembled_word;
    reg [7:0] word_index;
    reg [21:0] range_words;
    reg [4:0] outgoing_index;
    reg [15:0] turnaround;
    reg [31:0] result0, result1, result2;
    localparam NO_BYTE_LIMIT = CLOCK_HZ / 10;
    reg [23:0] no_byte_ticks;

    wire receiving = state <= CHECKSUM;
    wire use_pico = state == SEEK ? !host_available && pico_available : selected_pico;
    wire byte_ready = use_pico ? pico_available : host_available;
    wire [7:0] byte_in = use_pico ? pico_input : host_input;
    wire tx_valid = state == SEND && !(selected_pico ? pico_tx_busy : host_tx_busy);
    assign host_pop = receiving && !use_pico && byte_ready;
    assign pico_pop = receiving && use_pico && byte_ready;
    assign host_push = tx_valid && !selected_pico;
    assign pico_push = tx_valid && selected_pico;
    assign dot_valid = state == START_DOT;
    assign dot_weights = payload_first[0];
    assign dot_activations = {payload_first[2], payload_first[1]};
    assign memory_request = state == WRITE_WORD || state == READ_WORD || state == CHECK_RANGE;
    assign memory_write = state == WRITE_WORD;
    assign model_start = state == START_MODEL;
    assign model_reset = state == RESET_MODEL;
    assign model_token = address[15:0];
    assign model_output = address[16];
    wire [31:0] crc_out = ~checksum;

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

    function [31:0] crc_word;
        input [31:0] previous, value;
        begin
            crc_word = crc_byte(crc_byte(crc_byte(crc_byte(previous, value[7:0]),
                        value[15:8]), value[23:16]), value[31:24]);
        end
    endfunction

    wire [31:0] range_crc = crc_word(checksum, memory_result);
    wire [23:0] write_end = {1'b0, address[22:0]} + {8'b0, length};
    wire [23:0] range_end = {1'b0, address[22:0]} + payload_first[0][23:0];

    task respond;
        input [7:0] error;
        input [31:0] a, b, c;
        begin
            status <= error;
            result0 <= a;
            result1 <= b;
            result2 <= c;
            state <= TURN;
            turnaround <= (CLOCK_HZ / 1000000) * 24;
            checksum <= 32'hffffffff;
            outgoing_index <= 0;
        end
    endtask

    always @* begin
        case (outgoing_index)
            0: serial_output = 8'h5a;
            1: serial_output = 8'ha5;
            2: serial_output = command_code | 8'h80;
            3: serial_output = request_id;
            4: serial_output = 13;
            10: serial_output = status;
            11,12,13,14: serial_output = result0[8*(outgoing_index-11) +: 8];
            15,16,17,18: serial_output = result1[8*(outgoing_index-15) +: 8];
            19,20,21,22: serial_output = result2[8*(outgoing_index-19) +: 8];
            23,24,25,26: serial_output = crc_out[8*(outgoing_index-23) +: 8];
            default: serial_output = 0;
        endcase
    end

    always @(posedge clk) begin
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
                    selected_pico <= use_pico;
                    state <= SYNC;
                end
                SYNC: if (byte_ready) begin
                    if (byte_in == 8'h5a) begin
                        state <= HEADER;
                        header_index <= 0;
                        checksum <= 32'hffffffff;
                    end else if (byte_in != 8'ha5) state <= SEEK;
                end
                HEADER: if (byte_ready) begin
                    checksum <= crc_byte(checksum, byte_in);
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
                    checksum <= crc_byte(checksum, byte_in);
                    if (payload_index < 12)
                        payload_first[payload_index[3:2]][8*payload_index[1:0] +: 8] <= byte_in;
                    if ({6'b0,payload_index} == length - 1'b1) state <= CHECKSUM;
                    else payload_index <= payload_index + 1'b1;
                end
                CHECKSUM: if (byte_ready) begin
                    if (checksum_index == 3) begin
                        if ({byte_in, checksum_low} == ~checksum) state <= COMMAND;
                        else respond(BAD_CRC, 0, 0, 0);
                    end else begin
                        checksum_low[8*checksum_index +: 8] <= byte_in;
                        checksum_index <= checksum_index + 1'b1;
                    end
                end
                COMMAND: begin
                    memory_address <= address[22:2];
                    word_index <= 0;
                    if (command_code == 1 && length != 0 && !length[1:0] && !address[1:0] &&
                        address < 32'h800000 && write_end <= 24'h800000) state <= LOAD_WORD;
                    else if (command_code == 2 && !length && !address[1:0] && address < 32'h800000)
                        state <= READ_WORD;
                    else if (command_code == 3 && length == 4 && payload_first[0] != 0 &&
                        !payload_first[0][1:0] && payload_first[0] <= 32'h800000 &&
                        !address[1:0] && address < 32'h800000 && range_end <= 24'h800000) begin
                        checksum <= 32'hffffffff;
                        range_words <= payload_first[0][23:2];
                        state <= CHECK_RANGE;
                    end else if (command_code == 4 && length == 12) state <= START_DOT;
                    else if (command_code == 5 && !length) respond(OK, BUILD_ID, CLOCK_HZ, 8388608);
                    else if (command_code == 6 && !length && address[31:17] == 0) state <= START_MODEL;
                    else if (command_code == 7 && !length) state <= RESET_MODEL;
                    else respond(command_code >= 1 && command_code <= 7 ? BAD_RANGE : BAD_COMMAND, 0, 0, 0);
                end
                LOAD_WORD: state <= WRITE_WORD;
                WRITE_WORD: if (memory_complete) begin
                    if ({8'b0,word_index} == (length >> 2) - 1'b1) respond(OK, {16'b0,length}, 0, 0);
                    else begin
                        word_index <= word_index + 1'b1;
                        memory_address <= memory_address + 1'b1;
                        state <= LOAD_WORD;
                    end
                end
                READ_WORD: if (memory_complete) respond(OK, memory_result, 0, 0);
                CHECK_RANGE: if (memory_complete) begin
                    if (range_words == 1) respond(OK, ~range_crc, 0, 0);
                    else begin
                        range_words <= range_words - 1'b1;
                        memory_address <= memory_address + 1'b1;
                        checksum <= range_crc;
                    end
                end
                START_DOT: state <= WAIT_DOT;
                WAIT_DOT: if (dot_ready) respond(OK, {{17{dot_result[14]}},dot_result}, 0, 0);
                START_MODEL: state <= WAIT_MODEL;
                WAIT_MODEL: if (model_done) respond(model_status, model_result, model_checksum, model_cycles);
                RESET_MODEL: respond(OK, 0, 0, 0);
                TURN: begin
                    turnaround <= turnaround - 1'b1;
                    if (turnaround == 1) state <= SEND;
                end
                SEND: if (tx_valid) begin
                    if (outgoing_index >= 2 && outgoing_index < 23)
                        checksum <= crc_byte(checksum, serial_output);
                    outgoing_index <= outgoing_index + 1'b1;
                    if (outgoing_index == 26) state <= SEEK;
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
