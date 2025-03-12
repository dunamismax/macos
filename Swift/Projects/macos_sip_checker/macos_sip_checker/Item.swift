//
//  Item.swift
//  macos_sip_checker
//
//  Created by Stephen Sawyer on 3/12/25.
//

import Foundation
import SwiftData

@Model
final class Item {
    var timestamp: Date
    
    init(timestamp: Date) {
        self.timestamp = timestamp
    }
}
