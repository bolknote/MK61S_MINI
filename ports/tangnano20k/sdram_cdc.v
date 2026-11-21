// One request at a time. Weights request five consecutive words (including
// the scale), and attention requests all 32 coordinates of a K or V vector.
// Fetch aligned SDRAM bursts and retain the trailing line for the next request.
module tang_sdram_cdc (
    input wire clk, resetn, sdram_clk, sdram_resetn,
    input wire request, write,
    input wire [20:0] address,
    input wire [4:0] read_extra,
    input wire [31:0] data_in,
    output reg complete,
    output reg [31:0] data_out,
    output reg sdram_request, sdram_write,
    output wire sdram_next_read,
    output reg [20:0] sdram_address,
    output reg [31:0] sdram_data_in,
    input wire sdram_complete,
    input wire [31:0] sdram_data_out
);
    localparam IDLE = 0, PLAN = 1, CACHE = 2, FILL = 3, WRITE = 4;
    reg [2:0] state;
    reg [20:0] first_address;
    reg [1:0] line_distance;
    reg [5:0] words_left;
    reg [2:0] cache_offset, fill_offset, skip_words;
    reg [17:0] cached_line, fill_line;
    reg cache_valid;
    reg [31:0] line [0:7];

    // The mailbox is held until the last response is consumed. The epoch
    // crosses two registers before the memory side captures the descriptor.
    reg command_epoch, write_command;
    reg [20:0] command_address;
    reg [1:0] command_following_lines;
    reg [31:0] command_data;
    (* async_reg = "true" *) reg epoch_first, epoch_seen;
    reg epoch_consumed;
    reg [1:0] following_lines;
    reg [2:0] sdram_offset;
    reg [5:0] fill_left;
    wire [31:0] fetched;
    wire fetched_valid;
    wire [5:0] last_offset = {3'b0,address[2:0]} + {1'b0,read_extra};
    wire use_cache = cache_valid && cached_line == first_address[20:3];
    wire [17:0] fetch_line = first_address[20:3] + {17'b0,use_cache};
    wire [1:0] further_lines = line_distance - {1'b0,use_cache};
    wire fetch_needed = !use_cache || line_distance != 0;
    assign sdram_next_read = sdram_request && !sdram_write && following_lines != 0;

    // At most four aligned lines (32 words) are in flight. A second command
    // cannot publish until the first response, including its tail, is drained.
    tang_dot_fifo #(.WIDTH(32), .ADDRESS_BITS(5), .STREAM_READ(1)) responses (
        .write_clk(sdram_clk), .write_resetn(sdram_resetn),
        .push(sdram_request && sdram_complete), .write_data(sdram_data_out),
        .read_clk(clk), .read_resetn(resetn), .pop(state == FILL || state == WRITE),
        .available(), .valid(fetched_valid), .read_data(fetched)
    );

    always @(posedge sdram_clk) begin
        if (!sdram_resetn) begin
            epoch_first <= 0;
            epoch_seen <= 0;
            epoch_consumed <= 0;
            sdram_request <= 0;
        end else begin
            epoch_first <= command_epoch;
            epoch_seen <= epoch_first;
            if (epoch_seen != epoch_consumed) begin
                epoch_consumed <= epoch_seen;
                sdram_request <= 1;
                sdram_write <= write_command;
                sdram_address <= command_address;
                sdram_data_in <= command_data;
                following_lines <= command_following_lines;
                sdram_offset <= 0;
            end else if (sdram_request && sdram_complete) begin
                sdram_offset <= sdram_offset + 1'b1;
                if (sdram_write || sdram_offset == 7) begin
                    if (sdram_write || following_lines == 0) sdram_request <= 0;
                    else begin
                        sdram_address <= sdram_address + 21'd8;
                        following_lines <= following_lines - 1'b1;
                    end
                end
            end
        end
    end

    always @(posedge clk) begin
        complete <= 0;
        if (!resetn) begin
            state <= IDLE;
            command_epoch <= 0;
            cache_valid <= 0;
        end else begin
            case (state)
            IDLE: if (request && !complete) begin
                if (write) begin
                    if (cache_valid && cached_line == address[20:3]) cache_valid <= 0;
                    command_address <= address;
                    command_data <= data_in;
                    write_command <= 1;
                    command_epoch <= !command_epoch;
                    state <= WRITE;
                end else begin
                    first_address <= address;
                    line_distance <= last_offset[4:3];
                    words_left <= {1'b0,read_extra} + 1'b1;
                    state <= PLAN;
                end
            end
            PLAN: begin
                cache_offset <= first_address[2:0];
                if (fetch_needed) begin
                    command_address <= {fetch_line,3'b0};
                    command_following_lines <= further_lines;
                    write_command <= 0;
                    command_epoch <= !command_epoch;
                    fill_left <= {1'b0,further_lines,3'b0} + 6'd8;
                    fill_line <= fetch_line;
                    fill_offset <= 0;
                    skip_words <= use_cache ? 3'd0 : first_address[2:0];
                end
                state <= use_cache ? CACHE : FILL;
            end
            CACHE: begin
                data_out <= line[cache_offset];
                complete <= 1;
                cache_offset <= cache_offset + 1'b1;
                words_left <= words_left - 1'b1;
                if (words_left == 1) state <= IDLE;
                else if (cache_offset == 7) state <= FILL;
            end
            FILL: if (fetched_valid) begin
                line[fill_offset] <= fetched;
                fill_offset <= fill_offset + 1'b1;
                if (fill_offset == 7) fill_line <= fill_line + 1'b1;
                fill_left <= fill_left - 1'b1;
                if (skip_words != 0) skip_words <= skip_words - 1'b1;
                else if (words_left != 0) begin
                    data_out <= fetched;
                    complete <= 1;
                    words_left <= words_left - 1'b1;
                end
                if (fill_left == 1) begin
                    cached_line <= fill_line;
                    cache_valid <= 1;
                    state <= IDLE;
                end
            end
            WRITE: if (fetched_valid) begin
                complete <= 1;
                state <= IDLE;
            end
            default: state <= IDLE;
            endcase
        end
    end
endmodule
