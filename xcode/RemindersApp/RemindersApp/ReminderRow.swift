//
//  ReminderRow.swift
//  RemindersApp
//
//  Created by Stephen Sawyer on 4/10/25.
//

import SwiftUI
import SwiftData

struct ReminderRow: View {
    // Use @Bindable for direct two-way binding, especially useful for the toggle
    @Bindable var reminder: ReminderItem
    var editAction: () -> Void // Closure to trigger the edit sheet from ContentView

    @Environment(\.modelContext) private var modelContext // Needed if performing saves here (though often not required with @Bindable)
    @Environment(\.editMode) private var editMode // Access edit mode status (for potential UI changes)

    var body: some View {
        HStack(alignment: .top, spacing: 12) { // Align items to top, add spacing
            // Completion Toggle Button
            Button {
                 withAnimation(.snappy) { // Use a subtle animation
                    reminder.isCompleted.toggle()
                    // SwiftData handles save via @Bindable. No explicit save needed.
                 }
            } label: {
                Image(systemName: reminder.isCompleted ? "checkmark.circle.fill" : "circle")
                    .font(.title2) // Slightly larger toggle
                    .foregroundColor(reminder.isCompleted ? .gray : .accentColor) // Use accent color when incomplete
            }
            .buttonStyle(.plain) // Avoid default button background/border
            .accessibilityLabel(reminder.isCompleted ? "Mark as incomplete" : "Mark as complete") // Accessibility

            // Reminder Details (Title, Notes, Due Date)
            VStack(alignment: .leading, spacing: 3) { // Reduced spacing within text
                Text(reminder.title)
                    .font(.headline) // Give title more emphasis
                    .strikethrough(reminder.isCompleted, color: .secondary)
                    .foregroundStyle(reminder.isCompleted ? .secondary : .primary)

                if !reminder.notes.isEmpty {
                    Text(reminder.notes)
                        .font(.subheadline) // Slightly larger than caption
                        .foregroundStyle(.secondary)
                        .lineLimit(2) // Allow up to 2 lines for notes preview
                }

                if let dueDate = reminder.dueDate {
                    HStack(spacing: 4) {
                        Image(systemName: "calendar")
                        Text(dueDate, style: .date)
                        // Optionally show time if relevant
                        if Calendar.current.component(.hour, from: dueDate) != 0 || Calendar.current.component(.minute, from: dueDate) != 0 {
                             Text(dueDate, style: .time)
                        }
                    }
                    .font(.caption) // Keep date small
                    .foregroundStyle(dueDate < Date() && !reminder.isCompleted ? .red : .secondary) // Highlight overdue
                }
            }

            Spacer() // Push content to the left

            // Optional: Show an indicator if editing (like a disclosure indicator)
            if editMode?.wrappedValue.isEditing == false { // Don't show chevron if in edit mode typically
                 Image(systemName: "chevron.right")
                     .foregroundStyle(.tertiary)
                     .opacity(0.5) // Make it subtle
                     .padding(.leading, 5) // Add some space before it
            }
        }
        .padding(.vertical, 8) // Add more vertical padding for better spacing
        .opacity(reminder.isCompleted && editMode?.wrappedValue.isEditing == false ? 0.6 : 1.0) // Dim completed items slightly only when not editing
    }
}

// MARK: - Preview for ReminderRow

#Preview("Incomplete Task") {
    let config = ModelConfiguration(isStoredInMemoryOnly: true)
    let container = try! ModelContainer(for: ReminderItem.self, configurations: config)
    let sampleReminder = ReminderItem(title: "Sample Task", notes: "These are some detailed notes for the preview.", dueDate: Calendar.current.date(byAdding: .day, value: 2, to: Date()))
    container.mainContext.insert(sampleReminder)

    // Provide the container and padding for layout
    return ReminderRow(reminder: sampleReminder, editAction: { print("Edit action tapped") })
        .modelContainer(container)
        .padding(.horizontal)
}

#Preview("Completed Task") {
    let config = ModelConfiguration(isStoredInMemoryOnly: true)
    let container = try! ModelContainer(for: ReminderItem.self, configurations: config)
    let sampleReminder = ReminderItem(title: "Completed Task", notes: "This one is done.", dueDate: Calendar.current.date(byAdding: .day, value: -1, to: Date()), isCompleted: true)
    container.mainContext.insert(sampleReminder)

    return ReminderRow(reminder: sampleReminder, editAction: { print("Edit action tapped") })
        .modelContainer(container)
        .padding(.horizontal)
}
