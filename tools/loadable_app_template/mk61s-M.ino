// Arduino CLI требует точку входа sketch перед компиляцией исходников APP
// из src/. В итоговый образ overlay эти две функции не линкуются.
void setup() {}
void loop() {}
