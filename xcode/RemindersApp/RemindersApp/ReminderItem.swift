//
//  ReminderItem.swift
//  RemindersApp
//
//  Created by Stephen Sawyer on 4/10/25.
//

import Foundation
import SwiftData

@Model
final class ReminderItem {
    var title: String
    var notes: String
    var createdAt: Date // Keep track of when it was created
    var dueDate: Date? // Optional due date
    var isCompleted: Bool

    // Initializer with sensible defaults
    init(title: String = "New Reminder",
         notes: String = "",
         createdAt: Date = Date(), // Default to now
         dueDate: Date? = nil,    // Default to no due date
         isCompleted: Bool = false) { // Default to not completed
        self.title = title
        self.notes = notes
        self.createdAt = createdAt
        self.dueDate = dueDate
        self.isCompleted = isCompleted
    }

    // Helper computed property for sorting and display (optional but useful)
    // Note: This is not used directly in the provided views but could be helpful elsewhere.
    var displayDueDate: String {
        guard let date = dueDate else { return "No Due Date" }
        // Customize date format as needed
        return date.formatted(date: .numeric, time: .shortened)
    }
}
