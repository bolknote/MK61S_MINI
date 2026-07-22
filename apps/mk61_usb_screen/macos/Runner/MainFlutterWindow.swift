import Cocoa
import FlutterMacOS

class MainFlutterWindow: NSWindow {
  override func awakeFromNib() {
    let flutterViewController = FlutterViewController()
    let fixedWindowSize = NSSize(width: 768, height: 950)
    var windowFrame = self.frame
    windowFrame.origin.y += windowFrame.height - fixedWindowSize.height
    windowFrame.size = fixedWindowSize
    self.contentViewController = flutterViewController
    self.setFrame(windowFrame, display: true)
    self.styleMask.remove(.resizable)
    self.title = "MK61 USB Screen"

    RegisterGeneratedPlugins(registry: flutterViewController)

    super.awakeFromNib()
  }
}
