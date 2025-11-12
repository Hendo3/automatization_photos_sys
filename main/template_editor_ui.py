import customtkinter as ctk
import json
from pathlib import Path
import logging
from PIL import Image, ImageDraw, ImageFont, ImageTk
from tkinter import colorchooser, messagebox
import fitz # <-- IMPORTANTE: Nova biblioteca

# --- Configuração de Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Definição de Caminhos ---
BASE_DIR = Path(__file__).parent
TEMPLATE_CONFIG_FILE = BASE_DIR / "templates.json"
FONT_DIR = BASE_DIR / "fonts"
PICTURE_DIR = BASE_DIR / "pictures" # Agora vamos procurar PDFs aqui

# --- Listar Arquivos Disponíveis ---
try:
    # --- MUDANÇA AQUI: Lista PDFs, não imagens ---
    AVAILABLE_BASE_PDFS = sorted([f.name for f in PICTURE_DIR.iterdir() if f.suffix.lower() == '.pdf'])
    if not AVAILABLE_BASE_PDFS:
        AVAILABLE_BASE_PDFS = ["(Nenhum PDF encontrado em /pictures)"]
except FileNotFoundError:
    logger.warning(f"Pasta de imagens/PDFs '{PICTURE_DIR}' não encontrada.")
    AVAILABLE_BASE_PDFS = ["(Nenhuma pasta /pictures)"]

try:
    AVAILABLE_FONTS = sorted(["(Padrão do Template)"] + [f.name for f in FONT_DIR.iterdir() if f.suffix.lower() in ('.ttf', '.otf')])
except FileNotFoundError:
    logger.warning(f"Pasta de fontes '{FONT_DIR}' não encontrada.")
    AVAILABLE_FONTS = ["(Nenhuma fonte encontrada)"]

# (As funções load_templates e save_templates permanecem as mesmas)
def load_templates():
    if not TEMPLATE_CONFIG_FILE.exists(): return {}
    try:
        with open(TEMPLATE_CONFIG_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except Exception as e:
        logger.error(f"Erro ao carregar 'templates.json': {e}"); return {}

def save_templates(templates_data):
    try:
        with open(TEMPLATE_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(templates_data, f, indent=2, ensure_ascii=False)
        logger.info(f"Templates salvos com sucesso em '{TEMPLATE_CONFIG_FILE}'")
        return True
    except Exception as e:
        logger.error(f"Erro ao salvar 'templates.json': {e}"); return False

# --- NOVA FUNÇÃO HELPER ---
def _extract_pdf_page_to_pil(pdf_path: Path, page_num: int = 0, dpi: int = 150) -> Image.Image | None:
    """Extrai uma página de PDF e a converte para um objeto PIL.Image."""
    doc = None
    try:
        doc = fitz.open(pdf_path)
        if page_num >= len(doc):
            logger.error(f"PDF tem apenas {len(doc)} páginas. Não foi possível extrair a página {page_num + 1}.")
            return None
        
        page = doc[page_num]
        mat = fitz.Matrix(dpi / 72, dpi / 72) # Renderiza em 150 DPI para a UI
        pix = page.get_pixmap(matrix=mat, alpha=False) # alpha=False para RGB
        
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        return img
    except Exception as e:
        logger.error(f"Erro ao extrair página do PDF '{pdf_path.name}': {e}")
        return None
    finally:
        if doc:
            doc.close()

# --- Configuração da UI ---
ctk.set_appearance_mode("Dark") 
ctk.set_default_color_theme("blue")

class TemplateEditorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Editor Visual de Templates (Modo PDF-Base)")
        self.geometry("1200x800")
        
        self.templates_data = load_templates()
        self.original_pil_image = None
        self.display_pil_image = None
        self.display_ctk_image = None
        self.display_scale_factor = 1.0 # Fator de escala
        
        self.rect_start_x = None
        self.rect_start_y = None
        self.rect_id = None

        # --- Variáveis da UI ---
        self.selected_pdf_var = ctk.StringVar(value=AVAILABLE_BASE_PDFS[0])
        self.template_id_var = ctk.StringVar(value="") 
        self.pos_x_var = ctk.StringVar(value="0")
        self.pos_y_var = ctk.StringVar(value="0")
        self.max_width_var = ctk.StringVar(value="0")
        self.font_name_var = ctk.StringVar(value=AVAILABLE_FONTS[0])
        self.font_size_var = ctk.StringVar(value="50")
        self.color_var = ctk.StringVar(value="#FFFFFF")
        self.align_var = ctk.StringVar(value="left")

        # --- Layout ---
        self.grid_columnconfigure(0, weight=1) # Controles
        self.grid_columnconfigure(1, weight=5) # Imagem
        self.grid_rowconfigure(0, weight=1)

        # --- Painel de Controles (Esquerda) ---
        self.control_frame = ctk.CTkFrame(self, width=300)
        self.control_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.control_frame.pack_propagate(False) 

        ctk.CTkLabel(self.control_frame, text="Editor de Template", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10)

        # --- MUDANÇA AQUI: Carrega PDFs, não Imagens ---
        ctk.CTkLabel(self.control_frame, text="1. PDF de Referência (Base):").pack(anchor="w", padx=10)
        self.image_menu = ctk.CTkOptionMenu(self.control_frame, variable=self.selected_pdf_var, values=AVAILABLE_BASE_PDFS, command=self._on_pdf_select)
        self.image_menu.pack(fill="x", padx=10, pady=5)
        
        self.load_button = ctk.CTkButton(self.control_frame, text="Carregar PDF", command=self._load_pdf_page)
        self.load_button.pack(fill="x", padx=10, pady=(0, 10))

        # --- Campo de ID Lógico (do seu script anterior) ---
        ctk.CTkLabel(self.control_frame, text="2. Nome do Template (ID):", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10)
        ctk.CTkLabel(self.control_frame, text="(Ex: 'frente_agenda_template')").pack(anchor="w", padx=10, pady=(0,5))
        self.template_id_entry = ctk.CTkEntry(self.control_frame, textvariable=self.template_id_var)
        self.template_id_entry.pack(fill="x", padx=10, pady=5)
        
        # O resto do painel de controle (coords, fontes, etc.) é igual
        ctk.CTkLabel(self.control_frame, text="3. Desenhe o retângulo na imagem").pack(anchor="w", padx=10, pady=(10,0))
        coord_frame = ctk.CTkFrame(self.control_frame, fg_color="transparent")
        coord_frame.pack(fill="x", padx=10, pady=5)
        coord_frame.columnconfigure((0,1,2), weight=1)
        ctk.CTkLabel(coord_frame, text="Pos X:").grid(row=0, column=0)
        ctk.CTkLabel(coord_frame, text="Pos Y:").grid(row=1, column=0)
        ctk.CTkLabel(coord_frame, text="Largura:").grid(row=2, column=0)
        ctk.CTkEntry(coord_frame, textvariable=self.pos_x_var).grid(row=0, column=1, columnspan=2, sticky="ew")
        ctk.CTkEntry(coord_frame, textvariable=self.pos_y_var).grid(row=1, column=1, columnspan=2, sticky="ew")
        ctk.CTkEntry(coord_frame, textvariable=self.max_width_var).grid(row=2, column=1, columnspan=2, sticky="ew")

        ctk.CTkLabel(self.control_frame, text="4. Defina as Propriedades:").pack(anchor="w", padx=10, pady=(15, 5))
        
        ctk.CTkLabel(self.control_frame, text="Fonte Padrão:").pack(anchor="w", padx=10)
        self.font_menu = ctk.CTkOptionMenu(self.control_frame, variable=self.font_name_var, values=AVAILABLE_FONTS)
        self.font_menu.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(self.control_frame, text="Tamanho da Fonte:").pack(anchor="w", padx=10)
        self.font_size_entry = ctk.CTkEntry(self.control_frame, textvariable=self.font_size_var)
        self.font_size_entry.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(self.control_frame, text="Alinhamento:").pack(anchor="w", padx=10)
        self.align_menu = ctk.CTkOptionMenu(self.control_frame, variable=self.align_var, values=["left", "center", "right"])
        self.align_menu.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(self.control_frame, text="Cor (Hex):").pack(anchor="w", padx=10)
        self.color_entry = ctk.CTkEntry(self.control_frame, textvariable=self.color_var)
        self.color_entry.pack(fill="x", side="left", expand=True, padx=(10,5), pady=5)
        self.color_button = ctk.CTkButton(self.control_frame, text="...", width=30, command=self._pick_color)
        self.color_button.pack(side="right", padx=(0,10), pady=5)

        self.save_button = ctk.CTkButton(self.control_frame, text="SALVAR TEMPLATE", command=self._save_template)
        self.save_button.pack(side="bottom", fill="x", padx=10, pady=10)

        # --- Painel da Imagem (Direita) ---
        self.image_frame = ctk.CTkFrame(self)
        self.image_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        self.canvas = ctk.CTkCanvas(self.image_frame, background="#2B2B2B", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.canvas.bind("<Button-1>", self._on_mouse_press)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_release)
        
        # Carrega o primeiro PDF da lista, se existir
        if AVAILABLE_BASE_PDFS[0].endswith(".pdf"):
            self._on_pdf_select(self.selected_pdf_var.get())
            self._load_pdf_page()

    def _on_pdf_select(self, selected_pdf_name):
        """Chamado quando o usuário troca o PDF no dropdown."""
        # Tenta adivinhar o nome do template a partir do nome do PDF
        template_id = Path(selected_pdf_name).stem + "_template"
        self.template_id_var.set(template_id)
        
        # Verifica se um template com este ID já existe
        if template_id in self.templates_data:
            config = self.templates_data[template_id]
            self.pos_x_var.set(config.get("pos_x", 0))
            self.pos_y_var.set(config.get("pos_y", 0))
            self.max_width_var.set(config.get("max_width_pixels", 0))
            self.font_name_var.set(config.get("font_name", AVAILABLE_FONTS[0]))
            self.font_size_var.set(config.get("font_size", 50))
            self.color_var.set(config.get("color", "#FFFFFF"))
            self.align_var.set(config.get("align", "left"))
            self._load_pdf_page(draw_saved_rect=True)
        else:
            # Limpa os campos se for um template novo
            self.pos_x_var.set("0")
            self.pos_y_var.set("0")
            self.max_width_var.set("0")

    def _load_pdf_page(self, draw_saved_rect=False):
        """Extrai a primeira página do PDF e a exibe no canvas."""
        pdf_name = self.selected_pdf_var.get()
        pdf_path = PICTURE_DIR / pdf_name
        
        if not pdf_path.exists():
            logger.warning(f"PDF {pdf_name} não encontrado.")
            self.canvas.delete("all")
            return
            
        # --- MUDANÇA AQUI: Usa o helper do PyMuPDF ---
        self.original_pil_image = _extract_pdf_page_to_pil(pdf_path, page_num=0, dpi=300)
        # dpi=300 para que as coordenadas salvas sejam de alta resolução
        
        if not self.original_pil_image:
            self.canvas.delete("all")
            return
        
        # (O resto desta função é idêntico, apenas redimensiona e exibe a imagem PIL)
        canvas_width = self.image_frame.winfo_width()
        canvas_height = self.image_frame.winfo_height()
        
        if canvas_width < 50 or canvas_height < 50: 
            canvas_width, canvas_height = 800, 750 

        self.original_width, self.original_height = self.original_pil_image.size
        
        ratio = min(canvas_width / self.original_width, canvas_height / self.original_height)
        self.display_width = int(self.original_width * ratio)
        self.display_height = int(self.original_height * ratio)
        
        self.display_scale_factor = self.original_width / self.display_width
        
        self.display_pil_image = self.original_pil_image.resize((self.display_width, self.display_height), Image.Resampling.LANCZOS)
        self.display_photo_image = ImageTk.PhotoImage(self.display_pil_image)
        
        self.canvas.delete("all")
        self.canvas.configure(width=self.display_width, height=self.display_height)
        self.canvas.create_image(0, 0, anchor="nw", image=self.display_photo_image)
        self.rect_id = None
        
        if draw_saved_rect:
            try:
                # Converte coords originais (salvas em 300dpi) para coords da tela
                x0 = int(float(self.pos_x_var.get()) / self.display_scale_factor)
                y0 = int(float(self.pos_y_var.get()) / self.display_scale_factor)
                x1 = x0 + int(float(self.max_width_var.get()) / self.display_scale_factor)
                y1 = y0 + int(float(self.font_size_var.get()) * 1.5 / self.display_scale_factor) 
                
                self.rect_start_x, self.rect_start_y = x0, y0
                self.rect_id = self.canvas.create_rectangle(x0, y0, x1, y1, outline="red", width=2, tags="rect")
            except Exception as e:
                logger.error(f"Erro ao desenhar retângulo salvo: {e}")

    # (As funções _on_mouse_press, _on_mouse_drag, _on_mouse_release, _update_coords, e _pick_color
    #  são idênticas ao seu script original e não precisam de mudança)
    def _on_mouse_press(self, event):
        self.rect_start_x = event.x
        self.rect_start_y = event.y
        if self.rect_id: self.canvas.delete("rect")
        self.rect_id = self.canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="red", width=2, tags="rect")
        self._update_coords(event.x, event.y, event.x, event.y)

    def _on_mouse_drag(self, event):
        if not self.rect_id: return
        x_now = min(max(event.x, 0), self.display_width)
        y_now = min(max(event.y, 0), self.display_height)
        self.canvas.coords(self.rect_id, self.rect_start_x, self.rect_start_y, x_now, y_now)
        self._update_coords(self.rect_start_x, self.rect_start_y, x_now, y_now)

    def _on_mouse_release(self, event):
        x_now = min(max(event.x, 0), self.display_width)
        y_now = min(max(event.y, 0), self.display_height)
        self._update_coords(self.rect_start_x, self.rect_start_y, x_now, y_now)

    def _update_coords(self, x0, y0, x1, y1):
        rect_x0 = min(x0, x1); rect_y0 = min(y0, y1); rect_x1 = max(x0, x1)
        orig_x = int(rect_x0 * self.display_scale_factor)
        orig_y = int(rect_y0 * self.display_scale_factor)
        orig_width = int((rect_x1 - rect_x0) * self.display_scale_factor)
        self.pos_x_var.set(str(orig_x)); self.pos_y_var.set(str(orig_y)); self.max_width_var.set(str(orig_width))

    def _pick_color(self):
        color_code = colorchooser.askcolor(title="Escolha uma cor")
        if color_code and color_code[1]: self.color_var.set(color_code[1])

    # (A função _save_template é do seu script anterior, que já salva com o ID lógico)
    def _save_template(self):
        template_id_name = self.template_id_var.get().strip()
        if not template_id_name:
            messagebox.showwarning("Erro", "Por favor, insira um 'Nome do Template (ID)'.")
            return
        try:
            config_data = {
                "comment": f"Template para {template_id_name}",
                "pos_x": int(self.pos_x_var.get()),
                "pos_y": int(self.pos_y_var.get()),
                "max_width_pixels": int(self.max_width_var.get()),
                "font_name": self.font_name_var.get() if self.font_name_var.get() != AVAILABLE_FONTS[0] else None,
                "font_size": int(self.font_size_var.get()),
                "color": self.color_var.get(),
                "align": self.align_var.get()
            }
            config_data = {k: v for k, v in config_data.items() if v is not None}
            self.templates_data[template_id_name] = config_data
            if save_templates(self.templates_data):
                messagebox.showinfo("Sucesso", f"Template para '{template_id_name}' salvo com sucesso!")
            else:
                messagebox.showerror("Erro", "Falha ao salvar o arquivo 'templates.json'.")
        except ValueError:
            messagebox.showwarning("Erro", "Tamanho da fonte, X, Y e Largura devem ser números inteiros.")
        except Exception as e:
            messagebox.showerror("Erro", f"Ocorreu um erro: {e}")

if __name__ == "__main__":
    app = TemplateEditorApp()
    app.mainloop()