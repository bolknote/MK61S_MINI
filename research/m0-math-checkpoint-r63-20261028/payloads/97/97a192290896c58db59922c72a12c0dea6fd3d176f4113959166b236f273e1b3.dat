#ifndef MK61_MANUAL_LIFETIME_HPP
#define MK61_MANUAL_LIFETIME_HPP

#include <new>
#include <utility>

namespace manual_lifetime {

// Статическое хранилище без конструктора и деструктора T. Оно занимает ровно
// sizeof(T) байт и позволяет запустить аппаратно-зависимый конструктор явно,
// уже после входа в Arduino setup(). construct() разрешено вызывать один раз.
template<typename T>
class Storage {
  public:
    Storage(void) = default;
    Storage(const Storage&) = delete;
    Storage& operator=(const Storage&) = delete;

    template<typename... Args>
    T& construct(Args&&... args) {
      return *::new (static_cast<void*>(bytes))
        T(std::forward<Args>(args)...);
    }

    T& get(void) {
      return *reinterpret_cast<T*>(bytes);
    }

    const T& get(void) const {
      return *reinterpret_cast<const T*>(bytes);
    }

    void destroy(void) {
      get().~T();
    }

  private:
    alignas(T) unsigned char bytes[sizeof(T)];
};

} // пространство имён manual_lifetime

#endif
