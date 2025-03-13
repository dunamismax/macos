//
//  SIPCheckerApp.swift
//  SIPChecker
//
//  Created by Your Name on Date
//

import SwiftUI
import Foundation
import Darwin

/// A simple detail result from one of the SIP checks.
struct SIPCheckDetail: Identifiable {
    let id = UUID()
    let method: String
    let result: Bool
    let info: String
}

/// The ViewModel performs all the SIP/SIP ALG checks.
class SIPCheckerViewModel: ObservableObject {
    @Published var isChecking: Bool = false
    @Published var sipAlgDetected: Bool? = nil
    @Published var details: [SIPCheckDetail] = []
    @Published var errorMessage: String? = nil

    /// Begin the SIP scanning process.
    func checkSIP() {
        DispatchQueue.main.async {
            self.isChecking = true
            self.sipAlgDetected = nil
            self.details.removeAll()
            self.errorMessage = nil
        }
        
        DispatchQueue.global(qos: .userInitiated).async {
            // Get default gateway using an improved method.
            guard let gateway = self.getDefaultGateway() else {
                DispatchQueue.main.async {
                    self.errorMessage = "Unable to determine default gateway."
                    self.isChecking = false
                }
                return
            }
            
            var detectionFound = false
            
            // 1) Local UDP check: try multiple attempts with unique branch identifiers.
            let udpAttempts = 3
            for attempt in 1...udpAttempts {
                let branch = "z9hG4bK-\(Int(Date().timeIntervalSince1970))-\(Int.random(in: 1000...9999))"
                let (udpDetected, udpInfo) = self.udpSIPCheck(gateway: gateway, branch: branch)
                self.addDetail(method: "UDP Check Attempt \(attempt)", result: udpDetected, info: udpInfo)
                if udpDetected {
                    detectionFound = true
                    break
                }
            }
            
            // 2) Local TCP checks on common SIP ports (5060 & 5061).
            let (tcp5060Detected, tcp5060Info) = self.tcpSIPCheck(gateway: gateway, port: 5060)
            self.addDetail(method: "TCP Check (5060)", result: tcp5060Detected, info: tcp5060Info)
            if tcp5060Detected { detectionFound = true }
            
            let (tcp5061Detected, tcp5061Info) = self.tcpSIPCheck(gateway: gateway, port: 5061)
            self.addDetail(method: "TCP Check (5061)", result: tcp5061Detected, info: tcp5061Info)
            if tcp5061Detected { detectionFound = true }
            
            // 3) **External ALG check** - send SIP OPTIONS to a public SIP server and see if headers are manipulated.
            let (extDetected, extInfo) = self.externalALGCheck()
            self.addDetail(method: "External ALG Check", result: extDetected, info: extInfo)
            if extDetected {
                detectionFound = true
            }
            
            DispatchQueue.main.async {
                self.sipAlgDetected = detectionFound
                self.isChecking = false
            }
        }
    }
    
    /// Append a detail result on the main thread.
    private func addDetail(method: String, result: Bool, info: String) {
        DispatchQueue.main.async {
            self.details.append(SIPCheckDetail(method: method, result: result, info: info))
        }
    }
    
    // MARK: - Default Gateway Retrieval
    
    /// Retrieves the default gateway using "route -n get default" with a fallback to "netstat -rn".
    private func getDefaultGateway() -> String? {
        // First, try using "route -n get default"
        if let routeOutput = runCommand(launchPath: "/usr/sbin/route", arguments: ["-n", "get", "default"]),
           let gateway = parseGatewayFromRouteOutput(routeOutput) {
            return gateway
        }
        // Fallback: try using "netstat -rn"
        if let netstatOutput = runCommand(launchPath: "/usr/sbin/netstat", arguments: ["-rn"]),
           let gateway = parseGatewayFromNetstatOutput(netstatOutput) {
            return gateway
        }
        return nil
    }
    
    /// Executes a system command and returns its output as a String.
    private func runCommand(launchPath: String, arguments: [String]) -> String? {
        let process = Process()
        process.launchPath = launchPath
        process.arguments = arguments
        
        let pipe = Pipe()
        process.standardOutput = pipe
        
        do {
            try process.run()
        } catch {
            return nil
        }
        process.waitUntilExit()
        
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        return String(data: data, encoding: .utf8)
    }
    
    /// Parses the output from "route -n get default" to extract the gateway.
    private func parseGatewayFromRouteOutput(_ output: String) -> String? {
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
    
    /// Parses the output from "netstat -rn" to extract the default gateway.
    private func parseGatewayFromNetstatOutput(_ output: String) -> String? {
        let lines = output.split(separator: "\n")
        for line in lines {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.hasPrefix("default") {
                let columns = trimmed.components(separatedBy: .whitespaces).filter { !$0.isEmpty }
                // On macOS, the gateway is typically the second column.
                if columns.count >= 2 {
                    return columns[1]
                }
            }
        }
        return nil
    }
    
    // MARK: - Local UDP Check
    
    /// UDP check: sends a SIP OPTIONS message with a unique branch and waits for a response from the local gateway.
    private func udpSIPCheck(gateway: String, branch: String) -> (Bool, String) {
        let sipMsg = """
        OPTIONS sip:dummy@\(gateway) SIP/2.0\r
        Via: SIP/2.0/UDP \(gateway):5060;branch=\(branch)\r
        Max-Forwards: 70\r
        From: <sip:tester@\(gateway)>;tag=12345\r
        To: <sip:dummy@\(gateway)>\r
        Call-ID: \(UUID().uuidString)@\(gateway)\r
        CSeq: 1 OPTIONS\r
        Content-Length: 0\r
        \r
        """
        let sockFD = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)
        if sockFD < 0 {
            return (false, "Failed to create UDP socket.")
        }
        
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
            return (false, "Failed to send UDP SIP OPTIONS.")
        }
        
        // Set a 5-second timeout for a response.
        var tv = timeval(tv_sec: 5, tv_usec: 0)
        setsockopt(sockFD, SOL_SOCKET, SO_RCVTIMEO, &tv, socklen_t(MemoryLayout<timeval>.size))
        var buffer = [UInt8](repeating: 0, count: 2048)
        let recvCount = recv(sockFD, &buffer, buffer.count, 0)
        if recvCount > 0,
           let response = String(bytes: buffer[0..<recvCount], encoding: .utf8) {
            close(sockFD)
            // Parse the branch from the Via header.
            if let responseBranch = self.parseBranch(from: response) {
                // If the branch in the response does NOT match the sent branch, SIP ALG might be interfering.
                if responseBranch != branch {
                    return (true, "Response branch (\(responseBranch)) differs from sent branch (\(branch)).")
                } else {
                    return (false, "Received valid response with matching branch.")
                }
            } else {
                return (false, "Received response but could not parse branch.")
            }
        }
        close(sockFD)
        return (false, "No UDP response received within timeout.")
    }
    
    // MARK: - Local TCP Check
    
    /// TCP check: attempts to open a connection on the given port to the local gateway.
    private func tcpSIPCheck(gateway: String, port: Int) -> (Bool, String) {
        let sockFD = socket(AF_INET, SOCK_STREAM, 0)
        if sockFD < 0 {
            return (false, "Failed to create TCP socket on port \(port).")
        }
        
        var addr = sockaddr_in()
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_port = in_port_t(UInt16(port)).bigEndian
        inet_pton(AF_INET, gateway, &addr.sin_addr)
        let addrSize = socklen_t(MemoryLayout<sockaddr_in>.size)
        
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
            return (true, "Successfully connected to TCP port \(port).")
        }
        close(sockFD)
        return (false, "Unable to connect to TCP port \(port).")
    }
    
    // MARK: - External ALG Check
    
    /// Sends a SIP OPTIONS message to a public SIP server (via UDP) to detect potential ALG rewriting.
    ///
    /// - Returns: (detected: Bool, info: String)  where `detected == true` means suspicious rewriting was found.
    private func externalALGCheck() -> (Bool, String) {
        // A public SIP server that responds to OPTIONS. You may need to change this if it no longer works.
        let serverDomain = "sip2sip.info"
        let serverPort: UInt16 = 5060
        
        // Resolve the server domain to an IP address via getaddrinfo.
        guard let serverIP = resolveHostToIP(host: serverDomain, port: serverPort) else {
            return (false, "Could not resolve \(serverDomain).")
        }
        
        let sockFD = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)
        if sockFD < 0 {
            return (false, "Failed to create UDP socket for external check.")
        }
        
        // Bind locally on any ephemeral port.
        // (Optional) We could set a specific local port, but ephemeral is usually fine.
        var localAddr = sockaddr_in()
        localAddr.sin_family = sa_family_t(AF_INET)
        localAddr.sin_port = 0 // ephemeral
        localAddr.sin_addr.s_addr = in_addr_t(INADDR_ANY).bigEndian
        let localAddrSize = socklen_t(MemoryLayout<sockaddr_in>.size)
        let bindResult = withUnsafePointer(to: &localAddr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { sockAddr in
                Darwin.bind(sockFD, sockAddr, localAddrSize)
            }
        }
        if bindResult != 0 {
            close(sockFD)
            return (false, "Failed to bind local socket for external check.")
        }
        
        // Create a unique branch ID.
        let branch = "z9hG4bK-\(Int(Date().timeIntervalSince1970))-\(Int.random(in: 1000...9999))"
        
        // Our FROM/TO domains can be arbitrary, but must reference the external server in the request URI if we want a valid response.
        let sipMsg = """
        OPTIONS sip:\(serverDomain) SIP/2.0\r
        Via: SIP/2.0/UDP 0.0.0.0:5060;branch=\(branch)\r
        Max-Forwards: 70\r
        From: <sip:tester@\(serverDomain)>;tag=12345\r
        To: <sip:\(serverDomain)>\r
        Call-ID: \(UUID().uuidString)@\(serverDomain)\r
        CSeq: 1 OPTIONS\r
        Contact: <sip:tester@\(serverDomain)>\r
        Content-Length: 0\r
        \r
        """
        
        // Send to the resolved server IP
        var destAddr = serverIP
        let sendResult = sipMsg.withCString { ptr -> ssize_t in
            withUnsafePointer(to: &destAddr) {
                $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { sockAddr in
                    sendto(sockFD, ptr, strlen(ptr), 0, sockAddr, socklen_t(MemoryLayout<sockaddr_in>.size))
                }
            }
        }
        if sendResult < 0 {
            close(sockFD)
            return (false, "Failed to send external SIP OPTIONS to \(serverDomain).")
        }
        
        // Set a 5-second timeout for receiving a response.
        var tv = timeval(tv_sec: 5, tv_usec: 0)
        setsockopt(sockFD, SOL_SOCKET, SO_RCVTIMEO, &tv, socklen_t(MemoryLayout<timeval>.size))
        
        // Wait for a response.
        var buffer = [UInt8](repeating: 0, count: 4096)
        let recvCount = recv(sockFD, &buffer, buffer.count, 0)
        close(sockFD)
        
        if recvCount <= 0 {
            return (false, "No response from \(serverDomain) within timeout.")
        }
        
        guard let response = String(bytes: buffer[0..<recvCount], encoding: .utf8) else {
            return (false, "Received unreadable response from \(serverDomain).")
        }
        
        // Parse the branch from the Via header in the response.
        if let responseBranch = parseBranch(from: response) {
            // If the branch in the response does NOT match the sent branch, SIP ALG might be interfering.
            if responseBranch != branch {
                return (true, "Branch changed from (\(branch)) to (\(responseBranch))—ALG suspected.")
            } else {
                return (false, "Received valid response with matching branch from \(serverDomain).")
            }
        } else {
            return (false, "Received response but could not parse branch from \(serverDomain).")
        }
    }
    
    /// Resolves a hostname and port to a sockaddr_in via getaddrinfo (IPv4 only).
    private func resolveHostToIP(host: String, port: UInt16) -> sockaddr_in? {
        var hints = addrinfo(
            ai_flags: 0,
            ai_family: AF_INET,       // IPv4
            ai_socktype: SOCK_DGRAM,  // We want a UDP socket
            ai_protocol: IPPROTO_UDP,
            ai_addrlen: 0,
            ai_canonname: nil,
            ai_addr: nil,
            ai_next: nil
        )
        
        var res: UnsafeMutablePointer<addrinfo>? = nil
        let portString = String(port)
        let err = getaddrinfo(host, portString, &hints, &res)
        if err != 0 {
            return nil
        }
        
        defer { freeaddrinfo(res) }
        guard let addrInfo = res else { return nil }
        
        let addrPtr = addrInfo.pointee.ai_addr!.withMemoryRebound(to: sockaddr_in.self, capacity: 1) { $0 }
        return addrPtr.pointee
    }
    
    // MARK: - Common SIP Header Parsing
    
    /// Simple parser to extract the branch parameter from the "Via:" header.
    private func parseBranch(from response: String) -> String? {
        let lines = response.components(separatedBy: "\r\n")
        for line in lines {
            if line.lowercased().hasPrefix("via:") {
                if let branchRange = line.range(of: "branch=") {
                    let branchSubstr = line[branchRange.upperBound...]
                    if let endIndex = branchSubstr.firstIndex(where: { $0 == ";" || $0.isWhitespace }) {
                        return String(branchSubstr[..<endIndex])
                    } else {
                        return String(branchSubstr)
                    }
                }
            }
        }
        return nil
    }
}

/// The main content view showing progress and results.
struct ContentView: View {
    @StateObject private var viewModel = SIPCheckerViewModel()
    
    var body: some View {
        VStack(spacing: 20) {
            if viewModel.isChecking {
                VStack(spacing: 10) {
                    ProgressView()
                        .progressViewStyle(CircularProgressViewStyle())
                        .scaleEffect(2.0)
                    Text("Scanning for SIP ALG…")
                        .font(.headline)
                }
            } else {
                if let error = viewModel.errorMessage {
                    Text("Error: \(error)")
                        .foregroundColor(.red)
                        .multilineTextAlignment(.center)
                } else if let detected = viewModel.sipAlgDetected {
                    Image(systemName: detected ? "xmark.seal.fill" : "checkmark.seal.fill")
                        .font(.system(size: 72))
                        .foregroundColor(detected ? .red : .green)
                    Text(detected ? "SIP ALG Detected" : "SIP ALG Not Detected")
                        .font(.title)
                        .foregroundColor(detected ? .red : .green)
                }
                
                // Show detailed log of each check.
                List(viewModel.details) { detail in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(detail.method)
                            .font(.headline)
                        Text(detail.info)
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                    }
                }
                .frame(height: 150)
                
                Button("Rescan") {
                    viewModel.checkSIP()
                }
                .padding(.top, 5)
            }
        }
        .padding()
        .onAppear {
            viewModel.checkSIP()
        }
    }
}

/// The main app entry point. The window is sized to be just big enough to display our results.
@main
struct SIPCheckerApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                .frame(minWidth: 350, idealWidth: 350, maxWidth: 350,
                       minHeight: 250, idealHeight: 300, maxHeight: 300)
        }
    }
}
