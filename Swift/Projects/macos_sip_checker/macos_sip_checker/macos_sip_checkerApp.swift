//
//  SIPCheckerApp.swift
//  SIPChecker
//
//  Created by Your Name on Date
//

import SwiftUI
import Foundation
import Darwin

@main
struct SIPCheckerApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                .frame(width: 400, height: 300)
        }
    }
}

struct ContentView: View {
    @StateObject private var viewModel = SIPCheckerViewModel()
    
    var body: some View {
        ZStack {
            // Do not override background so that the window uses the system dark mode colors.
            Color.clear
            if viewModel.isChecking {
                VStack(spacing: 20) {
                    ProgressView()
                        .progressViewStyle(CircularProgressViewStyle())
                        .scaleEffect(2.5)
                    Text("Checking for SIP…")
                        .font(.largeTitle)
                        .foregroundColor(.primary)
                }
            } else {
                VStack(spacing: 20) {
                    if viewModel.sipDetected {
                        Image(systemName: "xmark.seal.fill")
                            .font(.system(size: 72))
                            .foregroundColor(.red)
                        Text("SIP Detected")
                            .font(.system(size: 36, weight: .bold))
                            .foregroundColor(.red)
                    } else {
                        Image(systemName: "checkmark.seal.fill")
                            .font(.system(size: 72))
                            .foregroundColor(.green)
                        Text("SIP Not Detected")
                            .font(.system(size: 36, weight: .bold))
                            .foregroundColor(.green)
                    }
                }
            }
        }
        .onAppear {
            viewModel.checkSIP()
        }
    }
}

class SIPCheckerViewModel: ObservableObject {
    @Published var isChecking: Bool = true
    @Published var sipDetected: Bool = false
    
    func checkSIP() {
        DispatchQueue.global(qos: .userInitiated).async {
            let detected = self.performSIPCheck()
            DispatchQueue.main.async {
                self.sipDetected = detected
                self.isChecking = false
            }
        }
    }
    
    /// Perform SIP checking using two independent methods (UDP and TCP).
    private func performSIPCheck() -> Bool {
        guard let gateway = getDefaultGateway() else {
            return false
        }
        let udpResult = udpSIPCheck(gateway: gateway)
        let tcpResult = tcpSIPCheck(gateway: gateway)
        // Consider SIP detected if either method returns true.
        return udpResult || tcpResult
    }
    
    /// UDP check: send SIP OPTIONS messages multiple times and wait for a SIP response.
    private func udpSIPCheck(gateway: String) -> Bool {
        let attempts = 3
        for _ in 0..<attempts {
            if sendSIPOptions(gateway: gateway) {
                return true
            }
        }
        return false
    }
    
    /// Send a SIP OPTIONS message over UDP and check for a valid SIP/2.0 response.
    private func sendSIPOptions(gateway: String) -> Bool {
        let timestamp = Int(Date().timeIntervalSince1970)
        let branch = "z9hG4bK-\(timestamp)"
        let callID = "\(timestamp)@\(gateway)"
        let sipMsg = """
        OPTIONS sip:dummy@\(gateway) SIP/2.0\r
        Via: SIP/2.0/UDP \(gateway):5060;branch=\(branch)\r
        Max-Forwards: 70\r
        From: <sip:tester@\(gateway)>;tag=12345\r
        To: <sip:dummy@\(gateway)>\r
        Call-ID: \(callID)\r
        CSeq: 1 OPTIONS\r
        Content-Length: 0\r
        \r
        """
        
        let sockFD = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)
        if sockFD < 0 { return false }
        
        var addr = sockaddr_in()
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_port = in_port_t(5060).bigEndian
        inet_pton(AF_INET, gateway, &addr.sin_addr)
        let addrSize = socklen_t(MemoryLayout<sockaddr_in>.size)
        
        let sendResult = sipMsg.withCString { ptr -> ssize_t in
            withUnsafePointer(to: &addr) {
                $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { sockAddr in
                    sendto(sockFD, ptr, strlen(ptr), 0, sockAddr, addrSize)
                }
            }
        }
        if sendResult < 0 {
            close(sockFD)
            return false
        }
        
        // Set a 5-second timeout for receiving a response.
        var tv = timeval(tv_sec: 5, tv_usec: 0)
        setsockopt(sockFD, SOL_SOCKET, SO_RCVTIMEO, &tv, socklen_t(MemoryLayout<timeval>.size))
        
        var buffer = [UInt8](repeating: 0, count: 2048)
        let recvCount = recv(sockFD, &buffer, buffer.count, 0)
        if recvCount > 0,
           let response = String(bytes: buffer[0..<recvCount], encoding: .utf8) {
            close(sockFD)
            if response.contains("SIP/2.0") {
                return true
            }
        }
        close(sockFD)
        return false
    }
    
    /// TCP check: attempt a connection to port 5060 on the default gateway.
    private func tcpSIPCheck(gateway: String) -> Bool {
        let sockFD = socket(AF_INET, SOCK_STREAM, 0)
        if sockFD < 0 { return false }
        
        var addr = sockaddr_in()
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_port = in_port_t(5060).bigEndian
        inet_pton(AF_INET, gateway, &addr.sin_addr)
        let addrSize = socklen_t(MemoryLayout<sockaddr_in>.size)
        
        // Set a timeout for connect.
        var tv = timeval(tv_sec: 5, tv_usec: 0)
        setsockopt(sockFD, SOL_SOCKET, SO_SNDTIMEO, &tv, socklen_t(MemoryLayout<timeval>.size))
        setsockopt(sockFD, SOL_SOCKET, SO_RCVTIMEO, &tv, socklen_t(MemoryLayout<timeval>.size))
        
        let connectResult = withUnsafePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { sockAddr in
                connect(sockFD, sockAddr, addrSize)
            }
        }
        if connectResult == 0 {
            close(sockFD)
            return true
        }
        close(sockFD)
        return false
    }
    
    /// Retrieves the default gateway by executing "route -n get default" and parsing the output.
    private func getDefaultGateway() -> String? {
        let process = Process()
        process.launchPath = "/usr/sbin/route"
        process.arguments = ["-n", "get", "default"]
        
        let pipe = Pipe()
        process.standardOutput = pipe
        
        do {
            try process.run()
        } catch {
            return nil
        }
        process.waitUntilExit()
        
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        guard let output = String(data: data, encoding: .utf8) else { return nil }
        let lines = output.split(separator: "\n")
        for line in lines {
            if line.contains("gateway:") {
                let parts = line.split(separator: ":")
                if parts.count > 1 {
                    return parts[1].trimmingCharacters(in: .whitespaces)
                }
            }
        }
        return nil
    }
}
