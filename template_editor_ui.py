import customtkinter as ctk
import json
from pathlib import Path
import logging
from PIL import Image, ImageDraw, ImageFont, ImageTk
from tkinter import colorchooser, messagebox

# --- Configuração de Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Definição de Caminhos ---
BASE_DIR = Path(__file__).parent
TEMPLATE_CONFIG_FILE = BASE_DIR / "templates.json"
FONT_DIR = BASE_DIR / "fonts"
PICTURE_DIR = BASE_DIR / "pictures"

# --- Listar Arquivos Disponíveis ---
try:
    AVAILABLE_IMAGES = sorted([f.name for f in PICTURE_DIR.iterdir() if f.suffix.lower() in ('.jpg', '.png', '.jpeg')])
except FileNotFoundError:
    logger.warning(f"Pasta de imagens '{PICTURE_DIR}' não encontrada.")
    AVAILABLE_IMAGES = ["(Nenhuma imagem encontrada)"]

try:
    AVAILABLE_FONTS = sorted(["(Padrão do Template)"] + [f.name for f in FONT_DIR.iterdir() if f.suffix.lower() in ('.ttf', '.otf')])
except FileNotFoundError:
    logger.warning(f"Pasta de fontes '{FONT_DIR}' não encontrada.")
    AVAILABLE_FONTS = ["(Nenhuma fonte encontrada)"]

# --- Funções de Leitura/Escrita do JSON ---
def load_templates():
    """Carrega o templates.json, ou retorna um dict vazio se não existir."""
    if not TEMPLATE_CONFIG_FILE.exists():
        return {}
    try:
        with open(TEMPLATE_CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Erro ao carregar 'templates.json': {e}")
        return {}

def save_templates(templates_data):
    """Salva o dict de templates de volta no 'templates.json'."""
    try:
        with open(TEMPLATE_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(templates_data, f, indent=2, ensure_ascii=False)
        logger.info(f"Templates salvos com sucesso em '{TEMPLATE_CONFIG_FILE}'")
        return True
    except Exception as e:
        logger.error(f"Erro ao salvar 'templates.json': {e}")
        return False

# --- Configuração da UI ---
ctk.set_appearance_mode("Dark") # Dark mode é melhor para design
ctk.set_default_color_theme("blue")

class TemplateEditorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Editor Visual de Templates")
        self.geometry("1200x800")
        
        # --- Estado da Aplicação ---
        self.templates_data = load_templates()
        self.original_pil_image = None
        self.display_pil_image = None
        self.display_ctk_image = None
        self_display_scale_factor = 1.0
        
        # Coordenadas do retângulo (em pixels da *imagem exibida*)
        self.rect_start_x = None
        self.rect_start_y = None
        self.rect_id = None

        # --- Variáveis da UI ---
        self.selected_image_var = ctk.StringVar(value=AVAILABLE_IMAGES[0])
        self.pos_x_var = ctk.StringVar(value="0")
        self.pos_y_var = ctk.StringVar(value="0")
        self.max_width_var = ctk.StringVar(value="0")
        self.font_name_var = ctk.StringVar(value=AVAILABLE_FONTS[0])
        self.font_size_var = ctk.StringVar(value="50")
        self.color_var = ctk.StringVar(value="#FFFFFF")
        self.align_var = ctk.StringVar(value="left")

        # --- Layout Principal (2 Colunas) ---
        self.grid_columnconfigure(0, weight=1) # Painel de Controles
        self.grid_columnconfigure(1, weight=5) # Painel da Imagem
        self.grid_rowconfigure(0, weight=1)

        # --- Painel de Controles (Esquerda) ---
        self.control_frame = ctk.CTkFrame(self, width=300)
        self.control_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.control_frame.pack_propagate(False) # Impede o frame de encolher

        ctk.CTkLabel(self.control_frame, text="Editor de Template", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10)

        ctk.CTkLabel(self.control_frame, text="1. Selecione a Imagem Base:").pack(anchor="w", padx=10)
        self.image_menu = ctk.CTkOptionMenu(self.control_frame, variable=self.selected_image_var, values=AVAILABLE_IMAGES, command=self._on_image_select)
        self.image_menu.pack(fill="x", padx=10, pady=5)
        
        self.load_button = ctk.CTkButton(self.control_frame, text="Carregar Imagem", command=self._load_image)
        self.load_button.pack(fill="x", padx=10, pady=(0, 15))

        ctk.CTkLabel(self.control_frame, text="2. Desenhe o retângulo na imagem").pack(anchor="w", padx=10)

        # --- Coordenadas (Atualizadas pelo desenho) ---
        coord_frame = ctk.CTkFrame(self.control_frame, fg_color="transparent")
        coord_frame.pack(fill="x", padx=10, pady=5)
        coord_frame.columnconfigure((0,1,2), weight=1)
        ctk.CTkLabel(coord_frame, text="Pos X:").grid(row=0, column=0)
        ctk.CTkLabel(coord_frame, text="Pos Y:").grid(row=1, column=0)
        ctk.CTkLabel(coord_frame, text="Largura:").grid(row=2, column=0)
        
        ctk.CTkEntry(coord_frame, textvariable=self.pos_x_var).grid(row=0, column=1, columnspan=2, sticky="ew")
        ctk.CTkEntry(coord_frame, textvariable=self.pos_y_var).grid(row=1, column=1, columnspan=2, sticky="ew")
        ctk.CTkEntry(coord_frame, textvariable=self.max_width_var).grid(row=2, column=1, columnspan=2, sticky="ew")

        ctk.CTkLabel(self.control_frame, text="3. Defina as Propriedades:").pack(anchor="w", padx=10, pady=(15, 5))
        
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

        # --- Ações ---
        self.save_button = ctk.CTkButton(self.control_frame, text="SALVAR TEMPLATE", command=self._save_template)
        self.save_button.pack(side="bottom", fill="x", padx=10, pady=10)

        # --- Painel da Imagem (Direita) ---
        self.image_frame = ctk.CTkFrame(self)
        self.image_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")

        self.canvas = ctk.CTkCanvas(self.image_frame, background="#2B2B2B", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Binds para desenho
        self.canvas.bind("<Button-1>", self._on_mouse_press)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_release)
        
        # Carrega o primeiro template se ele já existir
        self._on_image_select(self.selected_image_var.get())
        self._load_image()

    def _on_image_select(self, selected_image_name):
        """Chamado quando o usuário troca a imagem no dropdown."""
        if selected_image_name in self.templates_data:
            config = self.templates_data[selected_image_name]
            self.pos_x_var.set(config.get("pos_x", 0))
            self.pos_y_var.set(config.get("pos_y", 0))
            self.max_width_var.set(config.get("max_width_pixels", 0))
            self.font_name_var.set(config.get("font_name", AVAILABLE_FONTS[0]))
            self.font_size_var.set(config.get("font_size", 50))
            self.color_var.set(config.get("color", "#FFFFFF"))
            self.align_var.set(config.get("align", "left"))
            
            # Precisamos carregar a imagem para desenhar o retângulo salvo
            self._load_image(draw_saved_rect=True)
        else:
            # Limpa os campos se for uma imagem nova
            self.pos_x_var.set("0")
            self.pos_y_var.set("0")
            self.max_width_var.set("0")

    def _load_image(self, draw_saved_rect=False):
        """Carrega a imagem selecionada e a exibe no canvas."""
        image_name = self.selected_image_var.get()
        image_path = PICTURE_DIR / image_name
        
        if not image_path.exists():
            logger.warning(f"Imagem {image_name} não encontrada.")
            self.canvas.delete("all") # Limpa o canvas
            return
            
        self.original_pil_image = Image.open(image_path)
        
        # Calcula o tamanho da imagem para caber no frame
        canvas_width = self.image_frame.winfo_width()
        canvas_height = self.image_frame.winfo_height()
        
        if canvas_width < 50 or canvas_height < 50: # Frame ainda não renderizado
            canvas_width, canvas_height = 800, 750 # Valores padrão

        self.original_width, self.original_height = self.original_pil_image.size
        
        # Calcula a proporção para caber
        ratio = min(canvas_width / self.original_width, canvas_height / self.original_height)
        self.display_width = int(self.original_width * ratio)
        self.display_height = int(self.original_height * ratio)
        
        # Armazena o fator de escala reverso
        self.display_scale_factor = self.original_width / self.display_width
        
        self.display_pil_image = self.original_pil_image.resize((self.display_width, self.display_height), Image.Resampling.LANCZOS)
        
        # Converte de PIL para PhotoImage (para o Canvas)
        self.display_photo_image = ImageTk.PhotoImage(self.display_pil_image)
        
        self.canvas.delete("all")
        self.canvas.configure(width=self.display_width, height=self.display_height)
        self.canvas.create_image(0, 0, anchor="nw", image=self.display_photo_image)
        self.rect_id = None
        
        if draw_saved_rect:
            # Converte coords originais para coords da tela
            try:
                x0 = int(float(self.pos_x_var.get()) / self.display_scale_factor)
                y0 = int(float(self.pos_y_var.get()) / self.display_scale_factor)
                x1 = x0 + int(float(self.max_width_var.get()) / self.display_scale_factor)
                # Tenta adivinhar uma altura
                y1 = y0 + int(float(self.font_size_var.get()) * 1.5) 
                
                self.rect_start_x, self.rect_start_y = x0, y0
                self.rect_id = self.canvas.create_rectangle(x0, y0, x1, y1, outline="red", width=2, tags="rect")
            except Exception as e:
                logger.error(f"Erro ao desenhar retângulo salvo: {e}")

    def _on_mouse_press(self, event):
        """Inicia o desenho do retângulo."""
        self.rect_start_x = event.x
        self.rect_start_y = event.y
        
        # Deleta o retângulo antigo se existir
        if self.rect_id:
            self.canvas.delete("rect")
            
        self.rect_id = self.canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="red", width=2, tags="rect")
        
        # Atualiza as coordenadas em tempo real
        self._update_coords(event.x, event.y, event.x, event.y)

    def _on_mouse_drag(self, event):
        """Atualiza o retângulo enquanto arrasta."""
        if not self.rect_id:
            return
            
        # Garante que o evento está dentro dos limites da imagem
        x_now = min(max(event.x, 0), self.display_width)
        y_now = min(max(event.y, 0), self.display_height)
        
        self.canvas.coords(self.rect_id, self.rect_start_x, self.rect_start_y, x_now, y_now)
        
        # Atualiza as coordenadas em tempo real
        self._update_coords(self.rect_start_x, self.rect_start_y, x_now, y_now)

    def _on_mouse_release(self, event):
        """Finaliza o desenho e atualiza as coordenadas."""
        x_now = min(max(event.x, 0), self.display_width)
        y_now = min(max(event.y, 0), self.display_height)
        
        self._update_coords(self.rect_start_x, self.rect_start_y, x_now, y_now)

    def _update_coords(self, x0, y0, x1, y1):
        """Atualiza os campos de texto com as coordenadas *originais*."""
        
        # Garante que x0 é sempre o canto superior esquerdo
        rect_x0 = min(x0, x1)
        rect_y0 = min(y0, y1)
        rect_x1 = max(x0, x1)
        
        # --- A MÁGICA ---
        # Converte as coordenadas da *tela* para as coordenadas da *imagem original*
        orig_x = int(rect_x0 * self.display_scale_factor)
        orig_y = int(rect_y0 * self.display_scale_factor)
        orig_width = int((rect_x1 - rect_x0) * self.display_scale_factor)
        
        self.pos_x_var.set(str(orig_x))
        self.pos_y_var.set(str(orig_y))
        self.max_width_var.set(str(orig_width))

    def _pick_color(self):
        """Abre um seletor de cores."""
        color_code = colorchooser.askcolor(title="Escolha uma cor")
        if color_code and color_code[1]: # (rgb_tuple, hex_string)
            self.color_var.set(color_code[1])

    def _save_template(self):
        """Salva a configuração atual no 'templates.json'."""
        image_name = self.selected_image_var.get()
        if not image_name or image_name == AVAILABLE_IMAGES[0]:
            messagebox.showwarning("Erro", "Nenhuma imagem válida selecionada.")
            return

        try:
            # Monta o objeto de configuração
            config_data = {
                "comment": f"Template para {image_name}",
                "pos_x": int(self.pos_x_var.get()),
                "pos_y": int(self.pos_y_var.get()),
                "max_width_pixels": int(self.max_width_var.get()),
                "font_name": self.font_name_var.get() if self.font_name_var.get() != AVAILABLE_FONTS[0] else None,
                "font_size": int(self.font_size_var.get()),
                "color": self.color_var.get(),
                "align": self.align_var.get()
            }
            
            # Remove chaves None (como font_name)
            config_data = {k: v for k, v in config_data.items() if v is not None}

            # Atualiza o dict principal
            self.templates_data[image_name] = config_data
            
            # Salva o arquivo JSON
            if save_templates(self.templates_data):
                messagebox.showinfo("Sucesso", f"Template para '{image_name}' salvo com sucesso!")
            else:
                messagebox.showerror("Erro", "Falha ao salvar o arquivo 'templates.json'.")

        except ValueError:
            messagebox.showwarning("Erro", "Tamanho da fonte, X, Y e Largura devem ser números inteiros.")
        except Exception as e:
            messagebox.showerror("Erro", f"Ocorreu um erro: {e}")

if __name__ == "__main__":
    app = TemplateEditorApp()
    app.mainloop()