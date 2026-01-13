"""
Progress Sidebar Widget - Shows wizard progress and navigation.
"""

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.reactive import reactive
from textual.widgets import Static
from textual.message import Message


class ProgressSidebar(Container):
    """
    Sidebar showing wizard progress.

    Features:
    - Shows all 4 groups
    - Highlights current group
    - Shows checkmarks for completed
    - Displays estimated time remaining
    - Clickable for navigation
    """

    current: reactive[int] = reactive(1)
    completed: reactive[set] = reactive(set, init=False)

    def __init__(
        self,
        current: int = 1,
        completed: set | None = None,
        *args,
        **kwargs,
    ) -> None:
        """Initialize sidebar with current group and completed set."""
        super().__init__(*args, **kwargs)
        self.current = current
        self.completed = completed if completed is not None else set()

    GROUPS = [
        (1, "Foundation", "Project & URL"),
        (2, "Interface", "CSS Selectors"),
        (3, "Integrations", "Optional services"),
        (4, "Finalize", "Tests & Save"),
    ]

    # Estimated minutes per group
    TIME_ESTIMATES = {1: 4, 2: 5, 3: 8, 4: 6}

    class GroupSelected(Message):
        """Emitted when user clicks a group."""

        def __init__(self, group: int) -> None:
            self.group = group
            super().__init__()

    def compose(self) -> ComposeResult:
        """Create the sidebar content."""
        yield Static("SETUP WIZARD", classes="sidebar-title")
        yield Vertical(
            *[self._create_group_item(g, name, desc) for g, name, desc in self.GROUPS],
            id="sidebar-groups",
        )
        yield Static(self._format_time_remaining(), id="time-remaining", classes="sidebar-footer")

    def _create_group_item(self, group: int, name: str, description: str) -> Static:
        """Create a single group item for the sidebar."""
        return SidebarItem(
            group=group,
            group_name=name,
            description=description,
            is_current=(group == self.current),
            is_completed=(group in self.completed),
        )

    def _format_time_remaining(self) -> str:
        """Calculate and format estimated time remaining."""
        remaining_groups = [g for g in range(self.current, 5) if g not in self.completed]
        total_minutes = sum(self.TIME_ESTIMATES.get(g, 0) for g in remaining_groups)

        if total_minutes == 0:
            return "Almost done!"
        elif total_minutes == 1:
            return "~1 min remaining"
        else:
            return f"~{total_minutes} min remaining"

    def watch_current(self, group: int) -> None:
        """React to current group changes."""
        if not self.is_mounted:
            return
        self._update_items()
        self._update_time()

    def watch_completed(self, completed: set) -> None:
        """React to completed groups changes."""
        if not self.is_mounted:
            return
        self._update_items()
        self._update_time()

    def _update_items(self) -> None:
        """Update all sidebar items."""
        groups = self.query("#sidebar-groups").first()
        if groups:
            for item in groups.query(SidebarItem):
                item.is_current = (item.group == self.current)
                item.is_completed = (item.group in self.completed)

    def _update_time(self) -> None:
        """Update time remaining display."""
        time_widget = self.query_one("#time-remaining", Static)
        time_widget.update(self._format_time_remaining())


class SidebarItem(Static):
    """
    A single item in the progress sidebar.

    Shows:
    - Icon: [>] current, [check] completed, [ ] pending
    - Group number and name
    - Description on hover (via tooltip)
    """

    is_current: reactive[bool] = reactive(False)
    is_completed: reactive[bool] = reactive(False)

    def __init__(
        self,
        group: int,
        group_name: str,
        description: str,
        is_current: bool = False,
        is_completed: bool = False,
    ) -> None:
        self.group = group
        self.group_name = group_name
        self.description = description
        super().__init__()
        self.is_current = is_current
        self.is_completed = is_completed
        self.tooltip = description

    def render(self) -> str:
        """Render the sidebar item."""
        if self.is_completed:
            icon = "[green]OK[/green]"
            style_class = "completed"
        elif self.is_current:
            icon = "[cyan]>[/cyan] "
            style_class = "current"
        else:
            icon = "  "
            style_class = "pending"

        return f"{icon} {self.group}. {self.group_name}"

    def watch_is_current(self, current: bool) -> None:
        """Update styles when current state changes."""
        self._update_classes()

    def watch_is_completed(self, completed: bool) -> None:
        """Update styles when completed state changes."""
        self._update_classes()

    def _update_classes(self) -> None:
        """Update CSS classes based on state."""
        self.remove_class("current", "completed", "pending")
        if self.is_completed:
            self.add_class("completed")
        elif self.is_current:
            self.add_class("current")
        else:
            self.add_class("pending")
        self.add_class("sidebar-item")

    def on_mount(self) -> None:
        """Set initial classes."""
        self._update_classes()

    def on_click(self) -> None:
        """Handle click to navigate to this group."""
        # Only allow navigation to completed groups or current+1
        parent = self.ancestors_with_self
        for ancestor in parent:
            if isinstance(ancestor, ProgressSidebar):
                if self.is_completed or self.group <= ancestor.current + 1:
                    self.post_message(ProgressSidebar.GroupSelected(self.group))
                break
