module tang_uart #(
    parameter BIT_CLOCKS = 27
) (
    input wire clk, resetn,
    input wire rx, rx_enable, pop,
    input wire [7:0] tx_data,
    input wire push,
    output wire [7:0] rx_data,
    output reg rx_ready,
    output reg tx = 1,
    output wire tx_busy
);
    localparam TIMER_BITS = $clog2(BIT_CLOCKS);
    reg [TIMER_BITS-1:0] tx_count;
    reg [3:0] tx_left;
    reg [7:0] tx_shift;
    assign tx_busy = tx_left != 0;

    always @(posedge clk) begin
        if (!resetn) begin
            tx <= 1;
            tx_left <= 0;
        end else if (!tx_busy) begin
            if (push) begin
                tx <= 0;
                tx_left <= 10;
                tx_shift <= tx_data;
                tx_count <= BIT_CLOCKS - 1;
            end
        end else if (tx_count != 0) begin
            tx_count <= tx_count - 1'b1;
        end else begin
            tx_count <= BIT_CLOCKS - 1;
            tx_left <= tx_left - 1'b1;
            tx <= tx_left <= 2 ? 1'b1 : tx_shift[0];
            tx_shift <= {1'b1, tx_shift[7:1]};
        end
    end

    reg [1:0] sync;
    reg [TIMER_BITS-1:0] rx_count;
    reg [3:0] rx_state;
    reg [7:0] rx_shift;
    reg [7:0] fifo [0:31];
    reg [5:0] write_pos, read_pos;
    wire full = (write_pos ^ 6'h20) == read_pos;
    wire enqueue = rx_enable && rx_state == 10 && rx_count == 0 && sync[1] && !full;
    wire dequeue = pop && rx_ready;
    wire [5:0] next_read = read_pos + 1'b1;
    assign rx_data = fifo[read_pos[4:0]];

    always @(posedge clk) begin
        sync <= {sync[0], rx};
        if (!resetn) begin
            sync <= 2'b11;
            rx_state <= 0;
            read_pos <= 0;
            write_pos <= 0;
            rx_ready <= 0;
        end else begin
            if (enqueue) begin
                fifo[write_pos[4:0]] <= rx_shift;
                write_pos <= write_pos + 1'b1;
            end
            if (dequeue) read_pos <= next_read;
            if (enqueue) rx_ready <= 1;
            else if (dequeue) rx_ready <= next_read != write_pos;
            if (!rx_enable) begin
                rx_state <= 0;
            end else if (rx_state == 0) begin
                if (!sync[1]) begin
                    rx_state <= 1;
                    rx_count <= BIT_CLOCKS / 2 - 1;
                end
            end else if (rx_count != 0) begin
                rx_count <= rx_count - 1'b1;
            end else begin
                rx_count <= BIT_CLOCKS - 1;
                if (rx_state == 1) begin
                    rx_state <= sync[1] ? 0 : 2;
                end else if (rx_state == 10) begin
                    rx_state <= 0;
                end else begin
                    rx_shift <= {sync[1], rx_shift[7:1]};
                    rx_state <= rx_state + 1'b1;
                end
            end
        end
    end
endmodule
