import SwiftUI
import CoreData

// MARK: - Main App

@main
struct TaskManagerApp: App {
    let persistenceController = PersistenceController.shared

    var body: some Scene {
        WindowGroup {
            TaskListView()
                .environment(\.managedObjectContext, persistenceController.container.viewContext)
                .preferredColorScheme(.dark) // ensures dark mode throughout
        }
    }
}

// MARK: - Persistence Controller

struct PersistenceController {
    static let shared = PersistenceController()
    
    let container: NSPersistentContainer

    init(inMemory: Bool = false) {
        // Make sure the name here matches your .xcdatamodeld filename
        container = NSPersistentContainer(name: "TaskManagerModel")
        if inMemory {
            container.persistentStoreDescriptions.first?.url = URL(fileURLWithPath: "/dev/null")
        }
        container.loadPersistentStores { storeDescription, error in
            if let error = error as NSError? {
                // Replace with robust error handling in production.
                fatalError("Unresolved error \(error), \(error.userInfo)")
            }
        }
    }
}

// MARK: - Core Data Task Entity
//
// In your Core Data model, create an entity "Task" with these properties:
// • id (UUID)
// • title (String)
// • notes (String)
// • createdAt (Date)
// • trashed (Boolean)
// Relationships:
// • parent (to-one, optional, destination: Task)
// • subtasks (to-many, destination: Task, inverse: parent)
//

extension Task {
    static func fetchRequestActive() -> NSFetchRequest<Task> {
        let request: NSFetchRequest<Task> = Task.fetchRequest() as! NSFetchRequest<Task>
        request.sortDescriptors = [NSSortDescriptor(key: "createdAt", ascending: true)]
        // Only show non-trashed top-level tasks.
        request.predicate = NSPredicate(format: "trashed == NO AND parent == nil")
        return request
    }
    
    static func fetchRequestTrash() -> NSFetchRequest<Task> {
        let request: NSFetchRequest<Task> = Task.fetchRequest() as! NSFetchRequest<Task>
        request.sortDescriptors = [NSSortDescriptor(key: "createdAt", ascending: true)]
        request.predicate = NSPredicate(format: "trashed == YES")
        return request
    }
    
    static func fetchRequestSubtasks(parent: Task) -> NSFetchRequest<Task> {
        let request: NSFetchRequest<Task> = Task.fetchRequest() as! NSFetchRequest<Task>
        request.sortDescriptors = [NSSortDescriptor(key: "createdAt", ascending: true)]
        request.predicate = NSPredicate(format: "parent == %@", parent)
        return request
    }
}

// MARK: - Nord Color Theme

extension Color {
    static let nord0 = Color(red: 46/255, green: 52/255, blue: 64/255)
    static let nord1 = Color(red: 59/255, green: 66/255, blue: 82/255)
    static let nord2 = Color(red: 67/255, green: 76/255, blue: 94/255)
    static let nord3 = Color(red: 76/255, green: 86/255, blue: 106/255)
    static let nord4 = Color(red: 216/255, green: 222/255, blue: 233/255)
    static let nord5 = Color(red: 229/255, green: 233/255, blue: 240/255)
    static let nord6 = Color(red: 236/255, green: 239/255, blue: 244/255)
    static let nord7 = Color(red: 143/255, green: 188/255, blue: 187/255)
    static let nord8 = Color(red: 136/255, green: 192/255, blue: 208/255)
    static let nord9 = Color(red: 129/255, green: 161/255, blue: 193/255)
    static let nord10 = Color(red: 94/255, green: 129/255, blue: 172/255)
    static let nord11 = Color(red: 191/255, green: 97/255, blue: 106/255)
    static let nord12 = Color(red: 208/255, green: 135/255, blue: 112/255)
    static let nord13 = Color(red: 235/255, green: 203/255, blue: 139/255)
    static let nord14 = Color(red: 163/255, green: 190/255, blue: 140/255)
    static let nord15 = Color(red: 180/255, green: 142/255, blue: 173/255)
}

// MARK: - Task List View

struct TaskListView: View {
    @Environment(\.managedObjectContext) private var viewContext
    @FetchRequest(fetchRequest: Task.fetchRequestActive()) private var tasks: FetchedResults<Task>
    
    @State private var showingAddTask = false
    @State private var showingTrash = false

    var body: some View {
        NavigationView {
            List {
                ForEach(tasks) { task in
                    NavigationLink(destination: TaskDetailView(task: task)) {
                        Text(task.title ?? "Untitled")
                            .foregroundColor(.nord4)
                    }
                }
                .onDelete(perform: deleteTasks)
            }
            .navigationTitle("Tasks")
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button(action: { showingTrash.toggle() }) {
                        Image(systemName: "trash")
                    }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(action: { showingAddTask.toggle() }) {
                        Image(systemName: "plus")
                    }
                }
            }
            .sheet(isPresented: $showingAddTask) {
                AddTaskView()
                    .environment(\.managedObjectContext, viewContext)
            }
            .sheet(isPresented: $showingTrash) {
                TrashView()
                    .environment(\.managedObjectContext, viewContext)
            }
            .background(Color.nord0)
        }
    }
    
    private func deleteTasks(offsets: IndexSet) {
        withAnimation {
            for index in offsets {
                let task = tasks[index]
                // Soft-delete by marking as trashed.
                task.trashed = true
            }
            do {
                try viewContext.save()
            } catch {
                print("Error saving context after delete: \(error.localizedDescription)")
            }
        }
    }
}

// MARK: - Add Task View

struct AddTaskView: View {
    @Environment(\.managedObjectContext) private var viewContext
    @Environment(\.presentationMode) var presentationMode

    @State private var title: String = ""
    @State private var notes: String = ""

    var body: some View {
        NavigationView {
            Form {
                Section(header: Text("Task Info").foregroundColor(.nord4)) {
                    TextField("Title", text: $title)
                        .foregroundColor(.nord4)
                    TextField("Notes", text: $notes)
                        .foregroundColor(.nord4)
                }
            }
            .navigationTitle("New Task")
            .navigationBarItems(leading: Button("Cancel") {
                presentationMode.wrappedValue.dismiss()
            }, trailing: Button("Save") {
                addTask()
                presentationMode.wrappedValue.dismiss()
            })
            .background(Color.nord0)
        }
    }

    private func addTask() {
        let newTask = Task(context: viewContext)
        newTask.id = UUID()
        newTask.title = title
        newTask.notes = notes
        newTask.createdAt = Date()
        newTask.trashed = false
        do {
            try viewContext.save()
        } catch {
            print("Error saving new task: \(error.localizedDescription)")
        }
    }
}

// MARK: - Task Detail View (Editing & Subtasks)

struct TaskDetailView: View {
    @Environment(\.managedObjectContext) private var viewContext
    @ObservedObject var task: Task

    @State private var title: String = ""
    @State private var notes: String = ""
    @State private var showingAddSubtask = false
    @FetchRequest var subtasks: FetchedResults<Task>
    
    init(task: Task) {
        self.task = task
        _title = State(initialValue: task.title ?? "")
        _notes = State(initialValue: task.notes ?? "")
        let request = Task.fetchRequestSubtasks(parent: task)
        _subtasks = FetchRequest(fetchRequest: request)
    }

    var body: some View {
        Form {
            Section(header: Text("Task Info").foregroundColor(.nord4)) {
                TextField("Title", text: $title)
                    .foregroundColor(.nord4)
                TextField("Notes", text: $notes)
                    .foregroundColor(.nord4)
            }
            Section(header: Text("Subtasks").foregroundColor(.nord4)) {
                List {
                    ForEach(subtasks) { subtask in
                        NavigationLink(destination: TaskDetailView(task: subtask)) {
                            Text(subtask.title ?? "Untitled")
                                .foregroundColor(.nord4)
                        }
                    }
                    .onDelete(perform: deleteSubtasks)
                }
                Button(action: { showingAddSubtask.toggle() }) {
                    Label("Add Subtask", systemImage: "plus")
                }
            }
        }
        .navigationTitle("Task Detail")
        .navigationBarItems(trailing: Button("Save") {
            saveChanges()
        })
        .sheet(isPresented: $showingAddSubtask) {
            AddSubtaskView(parentTask: task)
                .environment(\.managedObjectContext, viewContext)
        }
        .background(Color.nord0)
    }

    private func saveChanges() {
        task.title = title
        task.notes = notes
        do {
            try viewContext.save()
        } catch {
            print("Error saving task changes: \(error.localizedDescription)")
        }
    }
    
    private func deleteSubtasks(offsets: IndexSet) {
        for index in offsets {
            let subtask = subtasks[index]
            subtask.trashed = true
        }
        do {
            try viewContext.save()
        } catch {
            print("Error deleting subtask: \(error.localizedDescription)")
        }
    }
}

// MARK: - Add Subtask View

struct AddSubtaskView: View {
    @Environment(\.managedObjectContext) private var viewContext
    @Environment(\.presentationMode) var presentationMode
    var parentTask: Task

    @State private var title: String = ""
    @State private var notes: String = ""

    var body: some View {
        NavigationView {
            Form {
                Section(header: Text("Subtask Info").foregroundColor(.nord4)) {
                    TextField("Title", text: $title)
                        .foregroundColor(.nord4)
                    TextField("Notes", text: $notes)
                        .foregroundColor(.nord4)
                }
            }
            .navigationTitle("New Subtask")
            .navigationBarItems(leading: Button("Cancel") {
                presentationMode.wrappedValue.dismiss()
            }, trailing: Button("Save") {
                addSubtask()
                presentationMode.wrappedValue.dismiss()
            })
            .background(Color.nord0)
        }
    }

    private func addSubtask() {
        let newSubtask = Task(context: viewContext)
        newSubtask.id = UUID()
        newSubtask.title = title
        newSubtask.notes = notes
        newSubtask.createdAt = Date()
        newSubtask.trashed = false
        newSubtask.parent = parentTask
        do {
            try viewContext.save()
        } catch {
            print("Error saving subtask: \(error.localizedDescription)")
        }
    }
}

// MARK: - Trash View

struct TrashView: View {
    @Environment(\.managedObjectContext) private var viewContext
    @FetchRequest(fetchRequest: Task.fetchRequestTrash()) private var trashedTasks: FetchedResults<Task>
    @Environment(\.presentationMode) var presentationMode

    var body: some View {
        NavigationView {
            List {
                ForEach(trashedTasks) { task in
                    HStack {
                        Text(task.title ?? "Untitled")
                            .foregroundColor(.nord4)
                        Spacer()
                        Button(action: {
                            recoverTask(task)
                        }) {
                            Image(systemName: "arrow.uturn.left")
                        }
                    }
                }
                .onDelete(perform: deleteTasksPermanently)
            }
            .navigationTitle("Trash")
            .navigationBarItems(leading: Button("Done") {
                presentationMode.wrappedValue.dismiss()
            })
            .background(Color.nord0)
        }
    }
    
    private func recoverTask(_ task: Task) {
        task.trashed = false
        do {
            try viewContext.save()
        } catch {
            print("Error recovering task: \(error.localizedDescription)")
        }
    }
    
    private func deleteTasksPermanently(offsets: IndexSet) {
        for index in offsets {
            let task = trashedTasks[index]
            viewContext.delete(task)
        }
        do {
            try viewContext.save()
        } catch {
            print("Error permanently deleting task: \(error.localizedDescription)")
        }
    }
}//
//  task_manager_ios.swift
//  task_manager_ios
//
//  Created by Stephen Sawyer on 3/12/25.
//

