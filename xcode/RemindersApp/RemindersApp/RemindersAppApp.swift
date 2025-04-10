//
//  RemindersAppApp.swift
//  RemindersApp
//
//  Created by Stephen Sawyer on 4/10/25.
//

import SwiftUI
import SwiftData

@main
struct RemindersAppApp: App { // Renamed struct
    var sharedModelContainer: ModelContainer = {
        // Use the ReminderItem model
        let schema = Schema([
            ReminderItem.self,
        ])
        let modelConfiguration = ModelConfiguration(schema: schema, isStoredInMemoryOnly: false)

        do {
            return try ModelContainer(for: schema, configurations: [modelConfiguration])
        } catch {
            // Consider more robust error handling for a release build,
            // maybe logging or presenting an alert to the user.
            fatalError("Could not create ModelContainer: \(error)")
        }
    }()

    var body: some Scene {
        WindowGroup {
            ContentView(reminders: <#[ReminderItem]#>)
        }
        .modelContainer(sharedModelContainer)
    }
}
