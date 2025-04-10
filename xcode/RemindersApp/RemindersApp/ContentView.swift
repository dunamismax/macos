//
//  ContentView.swift
//  RemindersApp
//
//  Created by Stephen Sawyer on 4/10/25.
//

import SwiftUI
import SwiftData

struct ContentView: View {
    @Environment(\.modelContext) private var modelContext
    
    // Query reminders, sorted by completion status then creation date (newest first)
    @Query(sort: [SortDescriptor(\ReminderItem.isCompleted), SortDescriptor(\ReminderItem.createdAt, order: .reverse)])
    private var reminders: [ReminderItem]

    // State for presenting the Add/Edit sheet
    @State private var showingAddEditSheet = false
    // State to hold the reminder being edited (nil for adding new)
    @State private var reminderToEdit: ReminderItem? = nil

    var body: some View {
        NavigationSplitView {
            // Primary list of reminders
            List {
                ForEach(reminders) { reminder in
                    ReminderRow(reminder: reminder, editAction: {
                        editReminder(reminder)
                    })
                    .contentShape(Rectangle()) // Ensure the whole row area is interactive
                    .contextMenu { // Context menu for quick actions
                        Button("Edit") {
                            editReminder(reminder)
                        }
                        Button(reminder.isCompleted ? "Mark as Incomplete" : "Mark as Complete") {
                            toggleCompletion(reminder)
                        }
                        Divider()
                        Button("Delete", role: .destructive) {
                            deleteReminder(reminder)
                        }
                    }
                    // Uncomment the NavigationLink below if you want a dedicated detail view
                    // when a row is tapped, instead of relying solely on the sheet/context menu.
                    /*
                    NavigationLink(destination: ReminderDetailView(reminder: reminder)) { // Assumes ReminderDetailView exists
                         ReminderRow(reminder: reminder, editAction: {
                             editReminder(reminder)
                         })
                    }
                    .contextMenu { /* ... context menu buttons ... */ }
                    */
                }
                .onDelete(perform: deleteItems) // Enable swipe-to-delete on iOS/iPadOS
            }
            .navigationTitle("Reminders") // Set the title for the list view
            #if os(macOS)
            .navigationSplitViewColumnWidth(min: 250, ideal: 300) // Suggest a width for the sidebar on macOS
            #endif
            .toolbar {
                // Platform-specific toolbar items
                #if os(macOS)
                // Display reminder count on macOS toolbar (optional)
                ToolbarItem(placement: .navigationBarLeading) {
                     Text("\(reminders.count) \(reminders.count == 1 ? "reminder" : "reminders")")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                #else
                // Provide the standard EditButton on iOS for multi-select delete
                ToolbarItem(placement: .navigationBarLeading) {
                    EditButton()
                }
                #endif

                // Common Add button for all platforms
                ToolbarItem(placement: .primaryAction) { // Use adaptable placement
                    Button {
                        addNewReminder()
                    } label: {
                        Label("Add Reminder", systemImage: "plus.circle.fill") // Use filled icon for prominence
                           // .labelStyle(.iconOnly) // Uncomment if you prefer icon only on all platforms
                           // .font(.title3)      // Adjust size if needed
                    }
                    .keyboardShortcut("n", modifiers: .command) // Standard Cmd+N shortcut for New
                    .help("Add a new reminder (⌘N)") // Tooltip for macOS
                }
            }
            // Display message when no reminders exist
             .overlay {
                if reminders.isEmpty {
                    ContentUnavailableView {
                         Label("No Reminders", systemImage: "list.bullet.rectangle.portrait")
                    } description: {
                         Text("Add your first reminder using the + button.")
                    } actions: {
                         Button("Add Reminder") { addNewReminder() }
                             .buttonStyle(.borderedProminent) // Make the action clear
                     }
                }
            }

        } detail: {
            // Detail column content - provides context or instructions
            // Note: For a full release, you might want a more dedicated detail view here,
            // perhaps showing the selected reminder's full info, or keeping this placeholder.
            if let selectedReminder = reminderToEdit {
                // You could potentially show a read-only view of the selected reminder here
                 Text("Editing \"\(selectedReminder.title)\"...")
                    .navigationTitle(selectedReminder.title) // Update detail title when editing
            } else if !reminders.isEmpty {
                 Text("Select a reminder from the list or right-click (long-press on iOS) for options.")
                     .foregroundStyle(.secondary)
                    .navigationTitle("Details")
            } else {
                 Text("Add your first reminder using the '+' button.")
                     .foregroundStyle(.secondary)
                     .navigationTitle("Reminders") // Keep consistent title
            }
        }
        // Sheet modifier for presenting the add/edit view
        .sheet(isPresented: $showingAddEditSheet) {
            // Pass the modelContext environment and the reminder binding
            // The sheet inherits the context automatically if not explicitly passed.
            AddEditReminderView(reminderToEdit: $reminderToEdit)
                //.environment(\.modelContext, modelContext) // Usually not needed if parent has it
        }
    }

    // MARK: - Actions (Private Helper Functions)

    private func addNewReminder() {
        reminderToEdit = nil // Clear any potential item being edited
        showingAddEditSheet = true // Present the sheet for adding
    }

    private func editReminder(_ reminder: ReminderItem) {
        reminderToEdit = reminder // Set the item to be edited
        showingAddEditSheet = true // Present the sheet for editing
    }

    private func toggleCompletion(_ reminder: ReminderItem) {
        withAnimation {
            reminder.isCompleted.toggle()
            // SwiftData automatically saves changes triggered by UI bindings (@Bindable).
            // Explicit save might be needed for background changes, but generally not here.
            // try? modelContext.save()
        }
    }

    private func deleteReminder(_ reminder: ReminderItem) {
        withAnimation {
            modelContext.delete(reminder)
            // Consider adding error handling for deletion failure in production.
            // try? modelContext.save() // Usually not needed after delete.
        }
    }

    // Handles deletion from swipe action or Edit mode
    private func deleteItems(offsets: IndexSet) {
        withAnimation {
            // Map indices to the actual ReminderItem objects and delete them
            offsets.map { reminders[$0] }.forEach(modelContext.delete)
            // Consider adding error handling.
        }
    }
}

// MARK: - Preview

#Preview {
    // Create an in-memory container specifically for the preview
    let config = ModelConfiguration(isStoredInMemoryOnly: true)
    let container: ModelContainer
    do {
        container = try ModelContainer(for: ReminderItem.self, configurations: config)
        // Add sample data for a richer preview experience
        let sampleReminders = [
            ReminderItem(title: "Buy groceries", notes: "Milk, Eggs, Bread", isCompleted: false),
            ReminderItem(title: "Call Mom", dueDate: Calendar.current.date(byAdding: .day, value: 1, to: Date()), isCompleted: false),
            ReminderItem(title: "Finish report", notes: "Due by EOD", dueDate: Date(), isCompleted: true),
            ReminderItem(title: "Schedule dentist appointment", isCompleted: false)
        ]
        sampleReminders.forEach { container.mainContext.insert($0) }
    } catch {
        // If container creation fails in preview, show a simple error text
        fatalError("Failed to create preview container: \(error)")
    }

    // Return the ContentView embedded in the preview container
    return ContentView()
        .modelContainer(container)
}
