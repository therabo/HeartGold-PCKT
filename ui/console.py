from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.align import Align
from rich.table import Table
import questionary

console = Console()


def get_banner_panel() -> Panel:
    banner_text = r"""
    ██╗  ██╗███████╗ █████╗ ██████╗ ████████╗ ██████╗  ██████╗ ██╗     ██████╗ 
    ██║  ██║██╔════╝██╔══██╗██╔══██╗╚══██╔══╝██╔════╝ ██╔═══██╗██║     ██╔══██╗    
    ███████║█████╗  ███████║██████╔╝   ██║   ██║  ███╗██║   ██║██║     ██║  ██║
    ██╔══██║██╔══╝  ██╔══██║██╔══██╗   ██║   ██║   ██║██║   ██║██║     ██║  ██║
    ██║  ██║███████╗██║  ██║██║  ██║   ██║   ╚██████╔╝╚██████╔╝███████╗██████╔╝
    ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝    ╚═════╝  ╚═════╝ ╚══════╝╚═════╝ 
    """
    gradient_banner = Text()
    colors = ["bold #FFD700", "bold #FFC300", "bold #FF8C00", "bold #FF5733", "bold #C70039", "bold #900C3F",
              "bold #581845"]
    lines = banner_text.strip("\n").split("\n")
    for i, line in enumerate(lines):
        color = colors[i % len(colors)]
        gradient_banner.append(line + "\n", style=color)

    aligned_content = Align.center(gradient_banner, vertical="middle")

    panel = Panel(
        aligned_content,
        border_style="dim",
        title="[gold1]HeartGold-PCKT[/gold1]",
        subtitle="[cyan]Pokémon TCG Pocket Automation Suite[/cyan]",
        height=12,
        expand=False
    )
    return panel


def display_initial_screen():
    console.clear()
    console.print(get_banner_panel())


def display_assignment_summary_table(assignments: list, language_options: dict) -> Table:
    summary_table = Table(
        title="[bold cyan]Assignment Summary[/bold cyan]",
        border_style="magenta",
        title_justify="left",
        show_header=True,
        header_style="white"
    )
    summary_table.add_column("Pack Name", style="cyan", no_wrap=True)
    summary_table.add_column("Cover Pokémon", style="yellow")
    summary_table.add_column("Language", style="green")
    summary_table.add_column("Processes", justify="right", style="bold green")

    for pack_info, count, lang_code in assignments:
        summary_table.add_row(
            pack_info['packName'],
            pack_info['coverPokemon'],
            language_options[lang_code],
            str(count)
        )
    return summary_table


def generate_stats_table(pack_count: int, god_pack_count: int, rate: float) -> Table:
    stats_table = Table.grid(padding=(0, 3))
    stats_table.add_column(style="white")
    stats_table.add_column(justify="right", style="white")

    stats_table.add_row("Total Packs Opened:", f"[bold green]{pack_count}[/bold green]")
    stats_table.add_row("GodPacks Found:", f"[bold bright_magenta]{god_pack_count}[/bold bright_magenta]")
    stats_table.add_row("Current Rate:", f"[yellow]{rate:.2f}[/yellow] packs/min")

    return Panel(
        Align.center(stats_table, vertical="middle"),
        title="[bold cyan]Live Statistics[/bold cyan]",
        border_style="magenta",
        height=7
    )


def display_leveler_wait_message():
    header_text = "Leveler Processes are Running"
    console.print("\n" + "=" * 38)
    console.print(f"   {header_text}")
    console.print("=" * 38)
    console.print("[i] The main process will wait for them to complete automatically...")


def ask_main_menu_choice() -> str | None:
    return questionary.select(
        "What do you want to do?",
        choices=[
            questionary.Choice("Collector (Acquire and filter packs)", "collector"),
            questionary.Choice("Leveler (Level up godpack accounts)", "leveler"),
            questionary.Separator(),
            questionary.Choice("Exit", "exit")
        ],
        pointer="» ",
        use_indicator=True,
        instruction=" "
    ).ask()


def ask_leveler_process_count() -> int | None:
    print("\n--- Leveler Module Configuration ---")
    num_str = questionary.text(
        "How many Leveler processes to create? (0 to exit)",
        validate=lambda text: text.isdigit() or "Please enter a valid number.",
        default="0",
    ).ask()
    return int(num_str) if num_str is not None else None


def ask_collector_process_count() -> int | None:
    print("\n--- Collector Module Configuration ---")
    num_str = questionary.text(
        "How many Collector processes to create in total? (0 to exit)",
        validate=lambda text: text.isdigit() or "Please enter a valid number.",
        default="0"
    ).ask()
    return int(num_str) if num_str is not None else None


def ask_for_assignments(pack_list: list, language_options: dict, processes_to_assign: int) -> list:
    assignments = []
    while processes_to_assign > 0:
        print(f"\nProcesses remaining to assign: {processes_to_assign}")

        pack_choices = [
            questionary.Choice(f"{p['packName']} ({p['coverPokemon']})", value=p)
            for p in pack_list
        ]
        selected_pack = questionary.select(
            "Choose a pack for the next batch of processes:",
            choices=pack_choices,
            pointer="» ",
            use_indicator=True,
            instruction=" "
        ).ask()
        if selected_pack is None: break

        lang_choices = [questionary.Choice(name, value=code) for code, name in language_options.items()]
        selected_lang_code = questionary.select(
            "Choose the language for this batch:",
            choices=lang_choices,
            pointer="» ",
            instruction=" "
        ).ask()
        if selected_lang_code is None: break

        num_to_assign_str = questionary.text(
            f"How many processes for '{selected_pack['packName']}' in {language_options[selected_lang_code]}?",
            validate=lambda text: (
                                          text.isdigit() and 0 < int(text) <= processes_to_assign
                                  ) or f"Please enter a number between 1 and {processes_to_assign}.",
        ).ask()
        if num_to_assign_str is None: break
        num_to_assign_for_pack = int(num_to_assign_str)

        assignments.append((selected_pack, num_to_assign_for_pack, selected_lang_code))
        print(
            f"[+] Assigned {num_to_assign_for_pack} processes to '{selected_pack['packName']}' in {language_options[selected_lang_code]}."
        )
        processes_to_assign -= num_to_assign_for_pack
    return assignments


def confirm_start(message: str = "Do you want to start the processes with this configuration?") -> bool:
    return questionary.confirm(message).ask()


def display_leveler_summary_table(total_accounts: int) -> Table:
    summary_table = Table(
        title="[bold cyan]Leveler Operation Summary[/bold cyan]",
        border_style="magenta",
        title_justify="left",
        show_header=True,
        header_style="white"
    )
    summary_table.add_column("Task", style="cyan", no_wrap=True)
    summary_table.add_column("Value", justify="right", style="bold green")
    summary_table.add_row("Total Accounts to Level Up", str(total_accounts))
    return summary_table


def generate_leveler_stats_table(completed_count: int, total_count: int) -> Panel:
    stats_table = Table.grid(padding=(0, 3))
    stats_table.add_column(style="white")
    stats_table.add_column(justify="right", style="white")

    progress_text = f"[bold green]{completed_count}[/bold green] / {total_count}"
    stats_table.add_row("Accounts Leveled Up:", progress_text)

    return Panel(
        Align.center(stats_table, vertical="middle"),
        title="[bold cyan]Live Progress[/bold cyan]",
        border_style="magenta",
        height=5
    )
