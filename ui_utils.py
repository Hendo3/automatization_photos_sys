import customtkinter as ctk


class ScrollableDropdown(ctk.CTkToplevel):
    def __init__(self, attach_widget, values, command=None, height=200, width=None):
        super().__init__()
        
        self.attach_widget = attach_widget
        self.command = command
        self.values = values
        self.height = height
        self.width = width if width else attach_widget.winfo_width()
        
        # Configuração da Janela Flutuante
        self.overrideredirect(True) # Remove barra de título
        self.attributes('-topmost', True) # Sempre no topo
        self.withdraw() # Esconde inicialmete para calcular posição
        
        # Frame de Scroll
        self.scroll_frame = ctk.CTkScrollableFrame(self, height=self.height)
        self.scroll_frame.pack(fill="both", expand=True)
        
        # Renderiza os botões
        self._init_buttons()
        
        # Posiciona e Mostra
        self._update_geometry()
        self.deiconify()
        
        # Foco e Fechamento
        self.focus_set()
        self.bind("<FocusOut>", self._on_focus_out)
        self.bind("<Escape>", self._on_focus_out)
        
        # Bind no widget pai para fechar se clicar fora ou mover
        self.attach_widget.winfo_toplevel().bind("<Configure>", self._on_focus_out, add="+")

    def _init_buttons(self):
        for val in self.values:
            btn = ctk.CTkButton(
                self.scroll_frame, 
                text=val, 
                anchor="w",
                fg_color="transparent", 
                text_color=("black", "white"),
                hover_color=("gray70", "gray30"),
                command=lambda v=val: self._on_click(v)
            )
            btn.pack(fill="x", padx=2, pady=2)

    def _on_click(self, value):
        # Atualiza o widget pai (ComboBox ou Entry)
        if isinstance(self.attach_widget, ctk.CTkComboBox):
            self.attach_widget.set(value)
            if self.command: self.command(value)
        elif isinstance(self.attach_widget, ctk.CTkEntry):
            self.attach_widget.delete(0, 'end')
            self.attach_widget.insert(0, value)
            if self.command: self.command(value)
        elif hasattr(self.attach_widget, 'set'):
            self.attach_widget.set(value)
            if self.command: self.command(value)
            
        self.destroy()

    def _on_focus_out(self, event=None):
        # --- CORREÇÃO AQUI ---
        try:
            focused_widget = self.focus_get()
            
            # Se não houver foco ou se o foco for interno do dropdown, não fecha
            if focused_widget == self or str(focused_widget).startswith(str(self)):
                return
                
        except KeyError:
            # Se der KeyError (ex: foco foi para um messagebox ou diálogo do sistema),
            # significa que o foco saiu do nosso controle. Devemos fechar o dropdown.
            pass
        except Exception:
            # Qualquer outro erro de foco, fechamos por segurança
            pass

        self.destroy()

    def _update_geometry(self):
        self.update_idletasks()
        
        # Pega coordenadas absolutas do widget pai
        try:
            root_x = self.attach_widget.winfo_rootx()
            root_y = self.attach_widget.winfo_rooty()
            widget_height = self.attach_widget.winfo_height()
            
            # Define posição logo abaixo do widget
            self.geometry(f"{self.width}x{self.height}+{root_x}+{root_y + widget_height + 2}")
        except Exception:
            # Se o widget pai for destruído antes, evita erro
            self.destroy()

# Função helper para facilitar o uso
def attach_scrollable_dropdown(widget, values, command=None, height=200):
    def open_dropdown(event=None):
        # Evita abrir múltiplos dropdowns se já existir um
        for child in widget.winfo_toplevel().winfo_children():
            if isinstance(child, ScrollableDropdown):
                child.destroy()
        
        ScrollableDropdown(widget, values, command, height)
    
    widget.bind("<Button-1>", open_dropdown, add="+")
    
    for child in widget.winfo_children():
        child.bind("<Button-1>", open_dropdown, add="+")
        
def enable_scrollable_dropdown(widget, values, command=None, height=200):
    attach_scrollable_dropdown(widget, values, command, height)