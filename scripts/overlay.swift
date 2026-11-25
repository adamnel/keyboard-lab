// Floats the keymap picture above every window and reloads it when the file changes.
// Clicks pass through it. Ctrl+Opt+Cmd+K hides or shows it; Ctrl-C in the terminal quits.
import AppKit
import Carbon.HIToolbox
import WebKit

let picture = URL(fileURLWithPath: CommandLine.arguments[1])
let app = NSApplication.shared
app.setActivationPolicy(.accessory)

let panel = NSPanel(contentRect: .zero, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
panel.level = .statusBar
panel.isOpaque = false
panel.backgroundColor = .clear
panel.alphaValue = 0.93
panel.ignoresMouseEvents = true
panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
let web = WKWebView(frame: .zero)
web.setValue(false, forKey: "drawsBackground")
panel.contentView = web

var loaded = Date.distantPast

func modified() -> Date {
    let attributes = try? FileManager.default.attributesOfItem(atPath: picture.path)
    return attributes?[.modificationDate] as? Date ?? .distantPast
}

/// Size the panel to the picture's aspect ratio, centred along the bottom of the main screen.
func reload() {
    guard let text = try? String(contentsOf: picture, encoding: .utf8), let screen = NSScreen.main else { return }
    var aspect = 0.4
    if let box = text.range(of: #"viewBox="0 0 [0-9.]+ [0-9.]+""#, options: .regularExpression) {
        let numbers = text[box].dropFirst(13).dropLast().split(separator: " ").compactMap { Double($0) }
        if numbers.count == 2 { aspect = numbers[1] / numbers[0] }
    }
    let area = screen.visibleFrame
    let width = min(area.width * 0.8, 1500)
    let frame = NSRect(x: area.midX - width / 2, y: area.minY + 24, width: width, height: width * aspect)
    panel.setFrame(frame, display: true)
    web.loadFileURL(picture, allowingReadAccessTo: picture.deletingLastPathComponent())
    loaded = modified()
}

func toggle() {
    if panel.isVisible { panel.orderOut(nil) } else { panel.orderFrontRegardless() }
}

var hotKey: EventHotKeyRef?
var pressed = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
InstallEventHandler(GetApplicationEventTarget(), { _, _, _ in toggle(); return noErr }, 1, &pressed, nil, nil)
RegisterEventHotKey(UInt32(kVK_ANSI_K), UInt32(controlKey | optionKey | cmdKey),
                    EventHotKeyID(signature: 0x4B_4C_41_42, id: 1), GetApplicationEventTarget(), 0, &hotKey)

signal(SIGINT) { _ in exit(0) }
reload()
panel.orderFrontRegardless()
Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { _ in if modified() > loaded { reload() } }
app.run()
