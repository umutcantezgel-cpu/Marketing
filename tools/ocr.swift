// Texterkennung mit Apples Vision-Framework (offline, ohne Zusatzsoftware).
// Aufruf: swift tools/ocr.swift bild1.png bild2.jpg ...
// Ausgabe: eine JSON-Zeile pro Bild: {"path": "...", "text": "..."}
import AppKit
import Foundation
import Vision

func emit(_ path: String, _ text: String) {
    let obj: [String: String] = ["path": path, "text": text]
    if let data = try? JSONSerialization.data(withJSONObject: obj),
       let line = String(data: data, encoding: .utf8) {
        print(line)
    }
}

for path in CommandLine.arguments.dropFirst() {
    guard let image = NSImage(contentsOf: URL(fileURLWithPath: path)),
          let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        emit(path, "")
        continue
    }
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["de-DE", "en-US"]
    request.usesLanguageCorrection = true
    try? VNImageRequestHandler(cgImage: cgImage, options: [:]).perform([request])
    let lines = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    emit(path, lines.joined(separator: "\n"))
}
