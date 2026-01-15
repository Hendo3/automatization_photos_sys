import json
import logging
from pathlib import Path
from tkinter import colorchooser, messagebox

# --- Módulos da Arquitetura ---
import config
import customtkinter as ctk
import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont, ImageTk
from schemas_validator import validate_data

# Configura logger centralizado
logger = config.setup_logging(__name__)

# Configurações UI
ctk.set_appearance_mode(config.UI_THEME_MODE)
ctk.set_default_color_theme(config.UI_COLOR_THEME)

class TemplateEditorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Editor de Templates (Preview Dinâmico)")
        self.geometry("1300x850")
        
        # --- Estado da Aplicação ---
        self.templates_data = self._load_templates_safe()
        
        # Imagens
        self.pdf_doc = None
        self.original_pil_image = None  # Imagem original (High Res)
        self.preview_pil_image = None   # Imagem com o texto desenhado
        self.display_image_tk = None    # Imagem convertida para Tkinter
        self.display_scale = 1.0        # Escala da visualização vs Original
        
        # Controle de Mouse
        self.rect_start_x = 0
        self.rect_start_y = 0
        self.rect_id = None  # ID do retângulo temporário no canvas

        # --- Variáveis Reativas (Triggers) ---
        self.selected_pdf = ctk.StringVar(value="")
        self.template_id_var = ctk.StringVar(value="")
        self.sample_text_var = ctk.StringVar(value="Nome Exemplo") # Texto para preview
        
        # Parâmetros do Template
        self.pos_x = ctk.StringVar(value="0")
        self.pos_y = ctk.StringVar(value="0")
        self.max_width = ctk.StringVar(value="500")
        self.font_size = ctk.StringVar(value="100")
        self.font_color = ctk.StringVar(value="#000000")
        self.font_name = ctk.StringVar(value=config.DEFAULT_FONT_NAME)
        self.align_var = ctk.StringVar(value="center")

        # Configura observers para Preview Dinâmico
        self._bind_preview_triggers()

        # --- Layout ---
        self._setup_layout()
        
        # Carrega Listas
        self._refresh_file_lists()

    def _load_templates_safe(self):
        """Carrega e valida templates usando o módulo central."""
        if not config.FILE_TEMPLATES_CONFIG.exists():
            return {}
        try:
            with open(config.FILE_TEMPLATES_CONFIG, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if validate_data(data, 'templates'):
                return data
            else:
                messagebox.showerror("Erro", "Arquivo templates.json corrompido. Backup recomendado.")
                return {}
        except Exception as e:
            logger.error(f"Erro ao carregar templates: {e}")
            return {}

    def _setup_layout(self):
        self.grid_columnconfigure(0, weight=0) # Sidebar fixa
        self.grid_columnconfigure(1, weight=1) # Área Canvas expansível
        self.grid_rowconfigure(0, weight=1)

        # === SIDEBAR (Controles) ===
        self.sidebar = ctk.CTkScrollableFrame(self, width=320, label_text="Controles")
        self.sidebar.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

        # 1. Seleção de Arquivo
        self._add_sidebar_section("1. PDF Base")
        self.pdf_menu = ctk.CTkOptionMenu(self.sidebar, variable=self.selected_pdf, command=self._on_pdf_change)
        self.pdf_menu.pack(fill="x", padx=5, pady=5)
        
        # 2. Identificação
        self._add_sidebar_section("2. Template ID")
        ctk.CTkEntry(self.sidebar, textvariable=self.template_id_var, placeholder_text="Ex: capa_agenda_2026").pack(fill="x", padx=5, pady=5)

        # 3. Texto de Exemplo (Novo)
        self._add_sidebar_section("3. Texto de Preview")
        ctk.CTkEntry(self.sidebar, textvariable=self.sample_text_var).pack(fill="x", padx=5, pady=5)

        # 4. Geometria (X, Y, W)
        self._add_sidebar_section("4. Geometria (Mouse ou Manual)")
        geo_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        geo_frame.pack(fill="x", padx=5, pady=5)
        self._create_labeled_entry(geo_frame, "Pos X:", self.pos_x, 0)
        self._create_labeled_entry(geo_frame, "Pos Y:", self.pos_y, 1)
        self._create_labeled_entry(geo_frame, "Largura:", self.max_width, 2)

        # 5. Estilização (Fonte e Cor)
        self._add_sidebar_section("5. Estilo da Fonte")
        
        # Fonte
        self.font_menu = ctk.CTkOptionMenu(self.sidebar, variable=self.font_name, values=[])
        self.font_menu.pack(fill="x", padx=5, pady=2)
        
        # Tamanho (Destaque conforme pedido)
        size_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        size_frame.pack(fill="x", padx=5, pady=5)
        ctk.CTkLabel(size_frame, text="Tamanho (px):").pack(side="left")
        ctk.CTkEntry(size_frame, textvariable=self.font_size, width=80).pack(side="right", fill="x", expand=True, padx=(5,0))

        # Alinhamento
        ctk.CTkLabel(self.sidebar, text="Alinhamento:", font=ctk.CTkFont(size=12)).pack(anchor="w", padx=5, pady=(5,0))
        self.align_menu = ctk.CTkSegmentedButton(self.sidebar, variable=self.align_var, values=["left", "center", "right"])
        self.align_menu.pack(fill="x", padx=5, pady=2)

        # Cor
        color_frame = ctk.CTkFrame(self.sidebar)
        color_frame.pack(fill="x", padx=5, pady=10)
        ctk.CTkLabel(color_frame, text="Cor (Hex):").pack(side="left", padx=5)
        ctk.CTkEntry(color_frame, textvariable=self.font_color, width=80).pack(side="left", padx=5)
        ctk.CTkButton(color_frame, text="🎨", width=40, command=self._pick_color).pack(side="right", padx=5)

        # Botão Salvar
        ctk.CTkButton(self.sidebar, text="💾 SALVAR TEMPLATE", command=self._save_template, fg_color="green").pack(fill="x", padx=5, pady=20, side="bottom")

        # === ÁREA PRINCIPAL (Canvas) ===
        self.canvas_frame = ctk.CTkFrame(self)
        self.canvas_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        
        self.canvas = ctk.CTkCanvas(self.canvas_frame, bg="#2b2b2b", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # Eventos do Canvas
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<Configure>", self._on_canvas_resize) # Responsividade

    # --- Helpers de UI ---
    def _add_sidebar_section(self, text):
        ctk.CTkLabel(self.sidebar, text=text, font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=5, pady=(15, 2))

    def _create_labeled_entry(self, parent, label, var, row):
        ctk.CTkLabel(parent, text=label).grid(row=row, column=0, sticky="w", pady=2)
        ctk.CTkEntry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", padx=5, pady=2)

    def _refresh_file_lists(self):
        # Listar PDFs
        config.ensure_directories()
        pdfs = sorted([f.name for f in config.DIR_PICTURES.iterdir() if f.suffix.lower() == '.pdf'])
        if pdfs:
            self.pdf_menu.configure(values=pdfs)
            self.selected_pdf.set(pdfs[0])
            self._on_pdf_change(pdfs[0])
        else:
            self.pdf_menu.configure(values=["(Sem PDFs em /pictures)"])

        # Listar Fontes
        fonts = sorted([f.name for f in config.DIR_FONTS.iterdir() if f.suffix.lower() in ('.ttf', '.otf')])
        if fonts:
            self.font_menu.configure(values=fonts)
            self.font_name.set(fonts[0] if fonts else config.DEFAULT_FONT_NAME)

    def _bind_preview_triggers(self):
        """Qualquer alteração nestas variáveis dispara o preview."""
        triggers = [self.sample_text_var, self.pos_x, self.pos_y, self.max_width, 
                    self.font_size, self.font_color, self.font_name, self.align_var]
        
        for var in triggers:
            # trace_add 'write' chama a função toda vez que o valor muda
            var.trace_add("write", lambda *args: self._update_preview_render())

    # --- Lógica de Renderização e Preview ---
    def _on_pdf_change(self, choice):
        if not choice or choice.startswith("("): return
        
        # Tenta carregar o template se já existir para este PDF
        potential_id = Path(choice).stem + "_template"
        self.template_id_var.set(potential_id)
        if potential_id in self.templates_data:
            self._load_template_data_into_ui(self.templates_data[potential_id])

        pdf_path = config.DIR_PICTURES / choice
        self._extract_pdf_high_res(pdf_path)
        self._update_display_image()

    def _extract_pdf_high_res(self, pdf_path):
        """Extrai em alta resolução (300DPI) para servir de base."""
        try:
            doc = fitz.open(pdf_path)
            page = doc[0]
            # 300 DPI = ~4.16x escala (72dpi base)
            pix = page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72))
            self.original_pil_image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            doc.close()
            # Inicializa o preview com a original
            self.preview_pil_image = self.original_pil_image.copy()
        except Exception as e:
            logger.error(f"Erro ao extrair PDF: {e}")

    def _update_preview_render(self):
        """
        O CORAÇÃO DO PREVIEW DINÂMICO.
        Desenha o texto na imagem PIL em memória e depois atualiza a tela.
        """
        if self.original_pil_image is None: return

        # 1. Copia a original para não sujar o buffer
        canvas_img = self.original_pil_image.copy()
        draw = ImageDraw.Draw(canvas_img)

        # 2. Coleta dados da UI (com tratamento de erro)
        try:
            x = int(self.pos_x.get())
            y = int(self.pos_y.get())
            w = int(self.max_width.get())
            size = int(self.font_size.get())
            color = self.font_color.get()
            text = self.sample_text_var.get()
            font_file = self.font_name.get()
            align = self.align_var.get()
        except ValueError:
            return # Ainda digitando número incompleto

        # 3. Configura a fonte
        font_path = config.DIR_FONTS / font_file
        if not font_path.exists(): font_path = config.DIR_FONTS / config.DEFAULT_FONT_NAME
        
        try:
            font = ImageFont.truetype(str(font_path), size)
            
            # 4. Lógica de Wrapping (Idêntica ao processar_agenda.py)
            lines = []
            words = text.split()
            current_line = ""
            for word in words:
                test_line = f"{current_line} {word}".strip()
                bbox = draw.textbbox((0,0), test_line, font=font)
                if (bbox[2] - bbox[0]) <= w:
                    current_line = test_line
                else:
                    lines.append(current_line)
                    current_line = word
            lines.append(current_line)

            # 5. Desenha Linha a Linha
            current_y = y
            # Altura da linha aproximada
            mask = font.getmask("hg")
            line_height = mask.size[1] * 1.25

            for line in lines:
                bbox = draw.textbbox((0,0), line, font=font)
                line_w = bbox[2] - bbox[0]
                
                draw_x = x
                if align == "center": draw_x = x + (w/2) - (line_w/2)
                elif align == "right": draw_x = x + w - line_w
                
                draw.text((draw_x, current_y), line, font=font, fill=color)
                current_y += line_height

            # Desenha a caixa limite (Bounding Box) em azul claro para referência visual
            draw.rectangle([x, y, x+w, current_y], outline="#00FFFF", width=2)

        except Exception as e:
            if config.IS_VERBOSE: logger.error(f"Erro render preview: {e}")

        self.preview_pil_image = canvas_img
        self._update_display_image()

    def _update_display_image(self):
        """Redimensiona a imagem PIL atual para caber no Canvas Tkinter."""
        if self.preview_pil_image is None: return

        # Dimensões do Canvas
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        
        # --- FIX: Fallbacks para inicialização (antes do mainloop geometry) ---
        # Antes só tínhamos fallback para width (cw), faltava para height (ch)
        if cw < 50: cw = 800 
        if ch < 50: ch = 600 

        iw, ih = self.preview_pil_image.size
        
        # Evita divisão por zero se a imagem carregada for corrompida (0x0)
        if iw == 0 or ih == 0: return

        # Calcula escala para "Fit" (caber na tela)
        self.display_scale = min(cw / iw, ch / ih)
        
        new_w = int(iw * self.display_scale)
        new_h = int(ih * self.display_scale)

        # --- FIX FINAL: Garante que nunca seja 0 (PIL lança ValueError se for 0) ---
        new_w = max(1, new_w)
        new_h = max(1, new_h)

        resized = self.preview_pil_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
        self.display_image_tk = ImageTk.PhotoImage(resized)

        self.canvas.delete("bg_img")
        self.canvas.create_image(0, 0, anchor="nw", image=self.display_image_tk, tags="bg_img")
        self.canvas.tag_lower("bg_img") # Garante que fique no fundo

    # --- Eventos do Canvas (Mouse) ---
    def _on_canvas_resize(self, event):
        # Debounce simples poderia ser usado aqui, mas vamos redesenhar direto
        self._update_display_image()

    def _on_canvas_click(self, event):
        self.rect_start_x = event.x
        self.rect_start_y = event.y
        if self.rect_id: self.canvas.delete(self.rect_id)
        # Cria retângulo visual (vermelho) temporário
        self.rect_id = self.canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="red", width=2)

    def _on_canvas_drag(self, event):
        if not self.rect_id: return
        self.canvas.coords(self.rect_id, self.rect_start_x, self.rect_start_y, event.x, event.y)

    def _on_canvas_release(self, event):
        if not self.original_pil_image: return
        
        # 1. Normaliza coordenadas do canvas
        x0, y0 = self.rect_start_x, self.rect_start_y
        x1, y1 = event.x, event.y
        
        start_x = min(x0, x1)
        start_y = min(y0, y1)
        width_tk = abs(x1 - x0)
        
        if width_tk < 10: return # Ignora cliques acidentais minúsculos

        # 2. Converte para coordenadas Reais da Imagem Original (300DPI)
        real_x = int(start_x / self.display_scale)
        real_y = int(start_y / self.display_scale)
        real_w = int(width_tk / self.display_scale)

        # 3. Atualiza as variáveis (isso vai disparar o _update_preview_render via trace)
        self.pos_x.set(str(real_x))
        self.pos_y.set(str(real_y))
        self.max_width.set(str(real_w))
        
        # Remove o retângulo vermelho pois agora o preview vai desenhar o texto e a caixa azul
        self.canvas.delete(self.rect_id)
        self.rect_id = None

    # --- Ações de Controle ---
    def _pick_color(self):
        color = colorchooser.askcolor(title="Escolha a cor do texto")
        if color and color[1]:
            self.font_color.set(color[1])

    def _load_template_data_into_ui(self, data):
        self.pos_x.set(data.get("pos_x", 0))
        self.pos_y.set(data.get("pos_y", 0))
        self.max_width.set(data.get("max_width_pixels", 300))
        self.font_size.set(data.get("font_size", 100))
        self.font_color.set(data.get("color", "#000000"))
        self.font_name.set(data.get("font_name") or config.DEFAULT_FONT_NAME)
        self.align_var.set(data.get("align", "center"))

    def _save_template(self):
        tid = self.template_id_var.get().strip()
        if not tid:
            messagebox.showwarning("Aviso", "Defina um ID para o Template.")
            return

        try:
            # Constrói o dict
            new_data = {
                "comment": f"Gerado pelo Editor para {tid}",
                "pos_x": int(float(self.pos_x.get())),
                "pos_y": int(float(self.pos_y.get())),
                "max_width_pixels": int(float(self.max_width.get())),
                "font_size": int(float(self.font_size.get())),
                "font_name": self.font_name.get(),
                "color": self.font_color.get(),
                "align": self.align_var.get()
            }
            
            # Valida APENAS este novo pedaço (truque: envolve num dict fake para validar estrutura)
            # Mas o schema valida o arquivo todo. Vamos confiar no salvamento e validação global.
            
            self.templates_data[tid] = new_data
            
            # Validação Final antes de Escrever
            if validate_data(self.templates_data, 'templates'):
                with open(config.FILE_TEMPLATES_CONFIG, 'w', encoding='utf-8') as f:
                    json.dump(self.templates_data, f, indent=2, ensure_ascii=False)
                messagebox.showinfo("Sucesso", f"Template '{tid}' salvo!")
                self._refresh_file_lists() # Atualiza dropdowns se necessário
            else:
                messagebox.showerror("Erro de Validação", "Os dados gerados são inválidos. Verifique o console (-v).")

        except ValueError:
            messagebox.showerror("Erro", "Certifique-se que as posições e tamanhos são números válidos.")

if __name__ == "__main__":
    app = TemplateEditorApp()
    app.mainloop()