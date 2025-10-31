
### **Product Brief: Project AIDA (AI-Driven Agile)**

#### **1. The Problem**

When using AI coding assistants for complex, multi-step tasks, developers face a significant challenge: context decay. The AI, much like a person, can lose track of the overarching goal when dealing with long, unstructured conversations. This leads to repeated clarifications, off-topic suggestions, and a lack of a clear, auditable trail of progress, forcing developers to manage project state in cumbersome text files or their own memory.

#### **2. The Solution**

Project AIDA introduces a structured, stateful workflow management system for AI-assisted development. It treats the AI as a remote team member, using a standard project management tool (Taiga) as the central "source of truth" for tasks.

The core of the system is the  **Scrum Master Agent** , an automated controller script that manages the entire agile process. It fetches tasks from a sprint board, translates them into focused prompts for the AI, and updates the board with progress, code, and comments. This creates a persistent, visual, and interactive workflow that keeps the Product Manager and the AI Developer perfectly in sync, while freeing the human from the mechanics of the agile process.

#### **3. Key Features & Value Proposition**

* **Structured Task Management:** Replaces messy `TODO` files with a clean, visual Scrum/Kanban board for managing the AI's work.
* **Automated Scrum Master:** A dedicated agent enforces agile processes, monitors for stagnation, and facilitates communication, allowing the Product Manager to focus on strategy, not mechanics.
* **Stateful & Focused Interaction:** By breaking work into discrete user stories and bugs, the AI is given one clear task at a time, dramatically reducing contextual drift.
* **Automated Progress Tracking:** The Scrum Master Agent updates task status on the board (e.g., from "In Progress" to "Ready for Review"), providing real-time visibility.
* **Interactive Feedback Loop:** Developers can review the AI's work directly in Taiga and provide feedback by "mentioning" the AI in a comment. The system automatically routes this feedback to the AI for corrections.
* **Portable & Repeatable Environments:** The entire Taiga environment is configured via scripts, allowing any developer to spin up a perfectly configured instance from a file committed to a repository.

#### **4. Target User & Roles**

* **The Product Manager (The Human User):** The visionary who defines the work by creating and prioritizing user stories and bugs.
* **The AI Developer:** The external AI coding assistant that executes the technical tasks.
* **The Scrum Master Agent (The AIDA System):** The automated process owner that facilitates the workflow.

#### **5. Success Metrics**

* Reduction in time spent re-explaining context to the AI.
* Increased focus for the Product Manager, measured by less time spent on manual process management.
* A clear, version-controlled audit trail of all AI-generated work within the project management tool.

---

### **Project Scope: AIDA Implementation**

#### **Project Goals**

To create a set of scripts that enable a local, self-hosted Taiga instance to function as an automated agile workflow system, managed by a Scrum Master Agent that directs an AI coding assistant.

#### **In-Scope Deliverables**

1. **Dockerized Taiga Environment:**
   * A `docker-compose.yml` file to launch a local Taiga instance and its required database.
   * A shell script to start and stop the environment cleanly.
2. **Configuration Management Scripts:**
   * **Exporter Script (`export_config.py`):** A Python script that connects to a manually configured Taiga project and exports its settings to a `taiga-config.json` file.
   * **Importer Script (`import_config.py`):** A Python script that reads the `taiga-config.json` file and automatically provisions a new, clean Taiga project.
3. **The Scrum Master Agent (`controller.py`):**
   * The core application logic that runs as a persistent service, embodying the principles and behaviors of a Scrum Master.
   * Includes modules for task acquisition, status updates, AI prompting, response parsing, history logging, and feedback detection.
   * Implements process enforcement, such as template validation and stagnation monitoring.

#### **Out-of-Scope for This Version**

* A graphical user interface (UI); all interaction is handled via the native Taiga UI and command-line scripts.
* Direct integration with IDEs.
* Support for project management tools other than Taiga.
* AI-driven project planning (e.g., the AI choosing its own tasks). The AI is a task executor only.

---

### **Developer Guide: Implementing AIDA**

#### **I. System Architecture & Roles**

The system is designed around a clear separation of roles, mimicking a real-world agile team:

1. **The Product Manager (The User):** Owns the *what* and the  *why* . Their sole responsibility is to create well-defined user stories and bugs in Taiga and to provide final acceptance of completed work.
2. **The AI Developer (The AI Assistant):** Owns the  *how* . This is an external LLM service that receives instructions and produces code. It has no awareness of the overall project, only the immediate task provided by the Scrum Master Agent.
3. **The Scrum Master Agent (The AI Controller):** Owns the  *process* . This is the Python application at the heart of AIDA. It communicates with both Taiga and the AI Developer to ensure the workflow is followed, impediments are raised, and work keeps moving.
4. **The Taiga Instance:** The shared workspace and single source of truth for all project tasks and their current state.

#### **II. The Scrum Master Agent: Principles and Behaviors**

The agent is programmed with a dual mandate, reflecting the intrinsic tension of the Scrum Master role.

**1. The Helpful Facilitator (Serves the Team):**

* **Protects from Distraction:** Shields the AI Developer from project-level noise by providing only one, well-defined task at a time.
* **Clarifies Requirements:** If the AI Developer is blocked and asks a question, the agent will post that question as a comment in Taiga and tag the `@ProductManager` for clarification.
* **Manages the Board:** Handles all the administrative work of updating statuses and logging communications, keeping the board clean and up-to-date.

**2. The Process Enforcer ("The Thorn in the Side"):**

* **Enforces "Definition of Ready":** The agent will refuse to start a task if it doesn't perfectly match the required User Story or Bug template. It will post a comment flagging the format error and notify the `@ProductManager`.
* **Monitors for Stagnation (The "Nudge"):** The agent tracks how long a task remains "In Progress." If a configurable time limit is exceeded, it will first "nudge" the AI Developer for a status update. If stagnation continues, it will escalate by posting an alert on the Taiga story for the `@ProductManager` to review.
* **Enforces "Definition of Done":** When prompting the AI, the agent will explicitly include the `Acceptance Criteria` from the story and instruct the AI to confirm its solution meets all of them.

#### **III. Environment Setup & Configuration Workflow**

(This section remains the same as your document, detailing the Initial Setup, Exporting, and Importing process.)

#### **IV. Core Controller Logic - API Interaction Guide**

(This section remains the same as your document, detailing Authentication, Fetching Tasks, Updating Status, Logging Output, and Detecting Feedback.)

#### **V. AI Interaction Protocol**

(This section remains the same as your document, detailing the Initial Task Prompt and Feedback Prompt.)

#### **VI. AIDA Interaction Specification: Rich Text Templates**

User Stories and Bugs should be represented in a structured
format.

**User Story Template**

---

**User Story:

**As a  *[role or person]* , I want *[desired state]* so
that  *[desired outcome/business value]* .

**Technical Notes:

** *[Describe any special technical considerations as an aside to the
team, enhancing context.]*

**Original Description:**

*[OPTIONAL. If the story was created via a help ticket, email or comment
there is likely a description. Keep this unless it’s wrong/confused. Omit this
entire Original Description section if no original description is provided.
This should ONLY be a verbatim quote in the requestor's words, not an invented
interpretation.]*

**Contact:

** *[OPTIONAL. The name of the person asking for the change. Omit this
Contact section if there is no contact provided.]*

**Links/Reference:

** *[A place for links and images. Add needed test/example links, one
per line with description. If the change is visual in nature, consider adding
an annotated picture to illustrate the change.]*

 **Testing Instructions:

** (to be completed by developer before handoff to QA Team)

**Acceptance Criteria:**

* *[List
  the first distinct criterion covering an actionable and testable aspect of
  the change.]*
* *[List
  the second distinct criterion.]*
* *[...add
  as many criteria as needed, one per line.]*

**Bug Template**

---

**Bug Behavior: **

*[Describe what’s happening wrong from the user’s
standpoint. Refer to any pictures in the Links/Reference section.]*

**Expected Behavior:

** *[This is the one acceptance criterion for the bug. Make it as
detailed as needed.]*

**Steps to Reproduce:**

 *[A numbered list of steps in sequence, including
logging in as a certain type of user, navigation, form submission, etc. Only
useful if accurate - don't guess. If not clear from the description, write
"Unclear".]*

1. *[First
   step]*
2. *[Second
   step]*
3. *[etc...]*

 **Links/Reference:

** *[A place for links and images. Add needed test/example links, one per
line with description. If the change is visual in nature, consider adding an
annotated picture to illustrate the issue.]*

 **Contact:

** *[OPTIONAL: The name of the person reporting the bug. Omit if not
specified.]*

**Supported Markdown (The Essentials)**

The templates you've designed wisely stick to the most
common and universally supported Markdown features, all of which Taiga handles
perfectly:

* Headers: Using # for
  titles (though your templates use bolding with __ which also
  works).
* Bold: Using **text** or __text__.
  Your templates use __Section Name__.
* Italics: Using *text* or _text_.
* Lists:
  * Unordered
    lists using *, -, or +.
  * Ordered
    lists using 1., 2., etc.
* Links: Using [display
  text](URL).
* Blockquotes: Using >
  quote. Your templates use this for the "Original Description"
  quote.
* Code
  Blocks: Using triple backticks (```) for multi-line code, which is
  essential for the AI's output.

**Key Limitations (What's Missing)**

Taiga's implementation is not "GitHub Flavored
Markdown" (GFM). The most notable feature that is not supported in
the default editor is:

* Tables: You
  cannot create tables using the standard Markdown pipe (|) syntax. This is
  a well-known limitation.
