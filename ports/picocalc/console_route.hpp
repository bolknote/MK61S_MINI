#ifndef MK61_PICOCALC_CONSOLE_ROUTE_HPP
#define MK61_PICOCALC_CONSOLE_ROUTE_HPP
#include <cstdint>
#include <initializer_list>
namespace picocalc::console {
enum class Channel : unsigned { USB,UART };
// One foreground shell. A partial line/upload/APP retains its transport;
// foreign text waits without being appended to that line. USB protocol
// packets may still be decoded before accept() sees terminal text.
class Route {
    int pending_[2]{-1,-1};
    Channel output_=Channel::UART,input_=Channel::UART;
    bool selected_=false;
    bool cr_[2]{};
    uint32_t switches_=0,received_[2]{};
public:
    template<class Backend> int read(Backend& backend,bool exclusive) {
        for(Channel source:{Channel::USB,Channel::UART}) {
            const unsigned index=(unsigned)source;
            if(exclusive && source!=output_ && (source==Channel::UART || pending_[index]>=0)) continue;
            int value=pending_[index];
            if(value>=0) pending_[index]=-1;
            else { value=backend.read(source);if(value>=0) ++received_[index]; }
            if(value>=0) { input_=source;return value; }
        }
        return -1;
    }
    bool accept(int value,bool exclusive) {
        if(value<0) return false;
        if(exclusive && selected_ && input_!=output_) {
            pending_[(unsigned)input_]=value;return false;
        }
        if(!selected_ || input_!=output_) ++switches_;
        output_=input_;selected_=true;return true;
    }
    bool skip_lf(int byte) {
        const unsigned source=(unsigned)output_;
        const bool skip=byte=='\n' && cr_[source];cr_[source]=byte=='\r';return skip;
    }
    Channel input() const { return input_; }
    Channel output() const { return output_; }
    bool selected() const { return selected_; }
    bool uart_output_enabled() const { return !selected_ || output_==Channel::UART; }
    uint32_t switches() const { return switches_; }
    uint32_t received(Channel source) const { return received_[(unsigned)source]; }
};
inline Route routing;
}
#endif
