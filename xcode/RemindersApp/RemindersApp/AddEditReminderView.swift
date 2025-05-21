//
//  AddEditReminderView.swift
//  RemindersApp
//
//  Created by Stephen Sawyer on 4/10/25.
//

import SwiftUI
import SwiftData

struct AddEditReminderView: View {
    @Environment(\.modelContext) private var modelContext
    @Environment(\.dismiss) var dismiss

    // Binding to the reminder being edited (passed from ContentView)
    // Will be nil if adding a new reminder.
    @Binding var reminderToEdit: ReminderItem?

    // Local state variables to hold the form data during editing/adding.
    @State private var title: String = ""
    @State private var notes: String = ""
    @State private var hasDueDate: Bool = false
    @State private var dueDate: Date = Calendar.current.startOfDay(for: Date()) // Default to today, start of day
    @State private var isCompleted: Bool = false // Keep track of completion status

    // Computed property to easily check if we are editing an existing item.
    var isEditing: Bool {
        reminderToEdit != nil
    }
    
    // Determine if the save button should be enabled (title must not be empty).
    var isSaveDisabled: Bool {
        title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var body: some View {
        // Use NavigationStack for title and toolbar buttons within the sheet.
        NavigationStack {
            Form {
                // Section for primary details
                Section {
                    TextField("Title", text: $title)
                        .accessibilityIdentifier("reminderTitleField") // For UI testing

                    // Use TextEditor for potentially longer notes
                    // TextField with axis: .vertical is also an option
                    ZStack(alignment: .topLeading) {
                         if notes.isEmpty {
                             Text("Notes (Optional)")
                                .foregroundColor(Color(uiColor: .placeholderText))
                                .padding(.top, 8) // Align with TextEditor padding
                                .padding(.leading, 5) // Align with TextEditor padding
                                .allowsHitTesting(false) // Let taps pass through to TextEditor
                         }
                         TextEditor(text: $notes)
                            .frame(minHeight: 100) // Give notes field some initial height
                            .accessibilityIdentifier("reminderNotesField")
                    }
                }

                // Section for due date configuration
                Section("Due Date") {
                    Toggle("Enable Due Date", isOn: $hasDueDate.animation())
                        .accessibilityIdentifier("dueDateToggle")

                    if hasDueDate {
                        // Show DatePicker only if the toggle is on.
                        DatePicker("Date", selection: $dueDate, displayedComponents: [.date, .hourAndMinute])
                            .datePickerStyle(.graphical) // Use a more visual style if desired, or .compact
                            .accessibilityIdentifier("dueDatePicker")
                    }
                }

                // Section to toggle completion status (relevant during editing)
                if isEditing {
                    Section("Status") {
                        Toggle("Completed", isOn: $isCompleted)
                             .accessibilityIdentifier("completedToggle")
                    }
                }
            }
            .navigationTitle(isEditing ? "Edit Reminder" : "New Reminder")
            .navigationBarTitleDisplayMode(.inline) // Keep title compact in sheet navigation bar
            .toolbar {
                // Cancel button (standard on the leading side)
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel", role: .cancel) { // Add role for clarity
                        dismiss() // Close the sheet without saving
                    }
                }
                // Done/Add button (standard on the trailing side)
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(isEditing ? "Done" : "Add") {
                        saveChanges()
                        dismiss() // Close the sheet after saving
                    }
                    .disabled(isSaveDisabled) // Disable if title is empty
                    .accessibilityIdentifier("saveButton")
                }
            }
            // Populate the form fields when the view appears if editing.
            .onAppear {
                guard let reminder = reminderToEdit, isEditing else {
                    // If adding a new reminder, the @State initializers provide defaults.
                    // We could potentially set a default due date here if desired for new items.
                    // e.g., dueDate = Calendar.current.date(byAdding: .day, value: 1, to: Date()) ?? Date()
                    return
                }
                
                // If editing, load data from the existing reminder into the @State variables.
                title = reminder.title
                notes = reminder.notes
                isCompleted = reminder.isCompleted
                if let existingDueDate = reminder.dueDate {
                    hasDueDate = true
                    dueDate = existingDueDate
                } else {
                    hasDueDate = false
                    // Optionally reset dueDate to default when toggling off
                    // dueDate = Calendar.current.startOfDay(for: Date())
                }
            }
        }
        #if os(macOS)
        // Suggest a reasonable size for the sheet on macOS.
        .frame(minWidth: 400, idealWidth: 450, minHeight: 400, idealHeight: 450)
        #endif
    }

    // MARK: - Save Logic

    private func saveChanges() {
        // Trim whitespace from title before saving
        let trimmedTitle = title.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedTitle.isEmpty else { return } // Should be prevented by disabled button, but double-check

        if let reminder = reminderToEdit {
            // Update the properties of the existing ReminderItem.
            reminder.title = trimmedTitle
            reminder.notes = notes // Notes can be empty
            reminder.dueDate = hasDueDate ? dueDate : nil // Set to nil if toggle is off
            reminder.isCompleted = isCompleted
            // SwiftData automatically tracks changes to managed objects.
            // An explicit save is generally not required here unless complex
            // multi-step operations are involved or for background tasks.
            print("Updated reminder: \(reminder.title)")

        } else {
            // Create a new ReminderItem instance.
            let newReminder = ReminderItem(
                title: trimmedTitle,
                notes: notes,
                createdAt: Date(), // Set creation date
                dueDate: hasDueDate ? dueDate : nil,
                isCompleted: false // New items are typically not completed initially
                // isCompleted: isCompleted // Or use the state if you allow setting completion on add
            )
            // Insert the new item into the model context.
            modelContext.insert(newReminder)
            print("Added new reminder: \(newReminder.title)")
        }

        // Optional: Explicit save if experiencing issues with auto-save or for certainty.
        // do {
        //     try modelContext.save()
        // } catch {
        //     // Handle save error appropriately in production (e.g., log, alert user)
        //     print("Failed to save changes: \(error)")
        // }
    }
}

// MARK: - Previews for AddEditReminderView

#Preview("Adding New") {
    // Preview for adding a new reminder
    // Need a dummy container for context, even if not saving in preview
    let config = ModelConfiguration(isStoredInMemoryOnly: true)
    let container = try! ModelContainer(for: ReminderItem.self, configurations: config)

    // Provide a constant binding of type ReminderItem? set to nil
    return AddEditReminderView(reminderToEdit: .constant(nil as ReminderItem?))
        .modelContainer(container) // Ensure context is available
}

#Preview("Editing Existing") {
    // Preview for editing an existing reminder
    let config = ModelConfiguration(isStoredInMemoryOnly: true)
    let container = try! ModelContainer(for: ReminderItem.self, configurations: config)
    // Create a sample item directly in the preview's context
    let sampleReminder = ReminderItem(title: "Existing Task", notes: "Details about the task that needs editing.", dueDate: Date(), isCompleted: false)
    container.mainContext.insert(sampleReminder) // Insert into preview context

    // Use a State variable within the Preview to hold the item, allowing the binding to work
    // Need a simple wrapper View for this @State variable.
    struct EditingPreviewWrapper: View {
        @State var reminder: ReminderItem? // State to hold the editable item

        init(reminder: ReminderItem?) {
            // Initialize the State variable with the sample item
            _reminder = State(initialValue: reminder)
        }

        var body: some View {
            // Pass the binding ($reminder) to the sheet view
            AddEditReminderView(reminderToEdit: $reminder)
        }
    }

    // Return the wrapper view within the model container
    return EditingPreviewWrapper(reminder: sampleReminder)
         .modelContainer(container)
}
