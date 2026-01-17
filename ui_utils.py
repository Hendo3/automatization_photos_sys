from __future__ import annotations

import tkinter as tk
from typing import Any, Callable, Iterable, Optional

import customtkinter as ctk


def attach_scrollable_dropdown(
    combo,
    values: Iterable[str],
    command: Optional[Callable[[str], None]] = None,
    height: int = 250,
):
    values = list(values)
    state: dict[str, Any] = {"win": None, "unbind_global": None, "bind_id": None}

    def _theme_pick(v, fallback: str) -> str:
        # CTk às vezes guarda cor como string ou como [light, dark]
        try:
            if isinstance(v, (list, tuple)) and len(v) >= 2:
                return v[1] if ctk.get_appearance_mode().lower() == "dark" else v[0]
            if isinstance(v, str) and v:
                return v
        except Exception:
            pass
        return fallback

    def _theme_get(path: list[str], fallback: str) -> str:
        try:
            node: Any = ctk.ThemeManager.theme
            for k in path:
                node = node[k]
            return _theme_pick(node, fallback)
        except Exception:
            return fallback

    def close_dropdown(_evt=None):
        unbind_global = state.get("unbind_global")
        if callable(unbind_global):
            try:
                unbind_global()
            except Exception:
                pass
        state["unbind_global"] = None
        state["bind_id"] = None

        win = state.get("win")
        if win is not None and win.winfo_exists():
            try:
                win.destroy()
            except Exception:
                pass
        state["win"] = None

    def open_dropdown(_evt=None):
        if state.get("win") is not None:
            close_dropdown()
            return

        # cores (fallbacks compatíveis com seu app)
        bg = _theme_get(["CTkFrame", "fg_color"], "#2b2b2b")
        fg = _theme_get(["CTkLabel", "text_color"], "#ffffff")
        sel_bg = _theme_get(["CTkButton", "hover_color"], "#3a3a3a")
        sel_fg = _theme_get(["CTkLabel", "text_color"], "#ffffff")

        win = ctk.CTkToplevel(combo.winfo_toplevel())
        state["win"] = win
        try:
            win.configure(fg_color=bg)
        except Exception:
            pass

        win.overrideredirect(True)
        try:
            win.attributes("-topmost", True)
        except Exception:
            pass

        x = combo.winfo_rootx()
        y = combo.winfo_rooty() + combo.winfo_height()
        w = combo.winfo_width()
        win.geometry(f"{max(200, w)}x{int(height)}+{x}+{y}")
        win.lift()

        frm = ctk.CTkFrame(win, corner_radius=0, fg_color=bg)
        frm.pack(fill="both", expand=True)

        vsb = ctk.CTkScrollbar(frm, orientation="vertical")

        lb = tk.Listbox(
            frm,
            activestyle="none",
            exportselection=False,
            yscrollcommand=vsb.set,
            bg=bg,
            fg=fg,
            selectbackground=sel_bg,
            selectforeground=sel_fg,
            highlightthickness=0,
            bd=0,
            relief="flat",
        )
        vsb.configure(command=lb.yview)

        vsb.pack(side="right", fill="y")
        lb.pack(side="left", fill="both", expand=True)

        for item in values:
            lb.insert("end", item)

        # pré-seleciona o valor atual (se existir)
        try:
            current_val = combo.get()
        except Exception:
            current_val = ""
        if current_val:
            try:
                idx = values.index(current_val)
                lb.selection_clear(0, "end")
                lb.selection_set(idx)
                lb.see(idx)
            except ValueError:
                pass

        def select_current(_evt=None):
            sel = lb.curselection()
            if not sel:
                return
            val = lb.get(sel[0])
            try:
                combo.set(val)
            except Exception:
                pass
            if command:
                command(val)
            close_dropdown()

        lb.bind("<ButtonRelease-1>", select_current)
        lb.bind("<Double-Button-1>", select_current)
        lb.bind("<Return>", select_current)
        win.bind("<Escape>", close_dropdown)
        try:
            lb.focus_set()
        except Exception:
            pass

        # Fecha ao clicar fora (robusto) — mas NÃO pode fechar no mesmo clique que abriu.
        top = combo.winfo_toplevel()
        entry = getattr(combo, "_entry", None)
        canvas = getattr(combo, "_canvas", None)

        def on_global_click(evt):
            wgt = getattr(evt, "widget", None)
            if state.get("win") is None:
                return

            # clique dentro do dropdown
            try:
                if wgt is not None and wgt.winfo_toplevel() == win:
                    return
            except Exception:
                pass

            # clique no próprio combo (inclui entry e canvas do CTkComboBox)
            if wgt is combo or (entry is not None and wgt is entry) or (canvas is not None and wgt is canvas):
                return

            close_dropdown()

        def bind_global_later():
            # garante que não captura o clique que abriu o dropdown
            bind_id = top.bind("<Button-1>", on_global_click, add=True)
            state["bind_id"] = bind_id

            def unbind_global():
                try:
                    top.unbind("<Button-1>", bind_id)
                except Exception:
                    pass

            state["unbind_global"] = unbind_global

        try:
            top.after(0, bind_global_later)
        except Exception:
            bind_global_later()

    # Clique/teclas no combo (área de texto)
    combo.bind("<Down>", open_dropdown, add=True)
    combo.bind("<ButtonRelease-1>", open_dropdown, add=True)

    entry = getattr(combo, "_entry", None)
    if entry is not None:
        entry.bind("<ButtonRelease-1>", open_dropdown, add=True)

    # Clique na seta/parte direita do CTkComboBox (Canvas tags)
    canvas = getattr(combo, "_canvas", None)
    if canvas is not None:
        try:
            canvas.tag_unbind("right_parts", "<Button-1>")
            canvas.tag_unbind("dropdown_arrow", "<Button-1>")
            canvas.tag_unbind("right_parts", "<ButtonRelease-1>")
            canvas.tag_unbind("dropdown_arrow", "<ButtonRelease-1>")
        except Exception:
            pass
        try:
            canvas.tag_bind("right_parts", "<ButtonRelease-1>", open_dropdown)
            canvas.tag_bind("dropdown_arrow", "<ButtonRelease-1>", open_dropdown)
        except Exception:
            pass

    combo.bind("<Destroy>", close_dropdown, add=True)
    return close_dropdown


if __name__ == "__main__":
    root = ctk.CTk()
    root.geometry("400x300")

    combo = ctk.CTkComboBox(root, values=["Option 1", "Option 2", "Option 3"])

    attach_scrollable_dropdown(
        combo,
        values=[f"Item {i}" for i in range(1, 51)],
        command=lambda val: print("Selected:", val),
        height=200,
    )
    combo.pack(pady=20, padx=20)
    root.mainloop()