#ifndef MK61_PICOCALC_IO_QUEUE_HPP
#define MK61_PICOCALC_IO_QUEUE_HPP
#include <atomic>
#include <cstddef>

namespace picocalc {
// One producer and one consumer. A full queue never overwrites unread bytes.
template<class T,std::size_t Capacity> class IoQueue {
    static_assert(Capacity>1,"queue needs an empty slot");
    T data_[Capacity]{};
    std::atomic<unsigned> read_{0},write_{0};
public:
    bool push(T value) {
        const unsigned at=write_.load(std::memory_order_relaxed);
        const unsigned next=(at+1)%Capacity;
        if(next==read_.load(std::memory_order_acquire)) return false;
        data_[at]=value;write_.store(next,std::memory_order_release);return true;
    }
    // The consumer owns the front entry until the callback returns.
    template<class Apply> bool consume(Apply apply) {
        const unsigned at=read_.load(std::memory_order_relaxed);
        if(at==write_.load(std::memory_order_acquire)) return false;
        apply(static_cast<const T&>(data_[at]));
        read_.store((at+1)%Capacity,std::memory_order_release);return true;
    }
    bool pop(T& value) {
        return consume([&](const T& item) {value=item;});
    }
    bool full() const {
        return (write_.load(std::memory_order_relaxed)+1)%Capacity==read_.load(std::memory_order_acquire);
    }
    bool empty() const { return read_.load(std::memory_order_acquire)==write_.load(std::memory_order_acquire); }
};
}
#endif
