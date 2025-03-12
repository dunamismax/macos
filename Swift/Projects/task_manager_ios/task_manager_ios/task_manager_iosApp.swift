//
//  task_manager_iosApp.swift
//  task_manager_ios
//
//  Created by Stephen Sawyer on 3/12/25.
//

import SwiftUI

@main
struct task_manager_iosApp: App {
    let persistenceController = PersistenceController.shared

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(\.managedObjectContext, persistenceController.container.viewContext)
        }
    }
}
