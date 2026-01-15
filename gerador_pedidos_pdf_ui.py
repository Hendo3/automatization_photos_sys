import json
import logging
import threading
from tkinter import messagebox

# --- Módulos da Arquitetura ---
import config
import customtkinter as ctk
import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont, ImageTk
from schemas_validator import validate_data
from ui_utils import attach_scrollable_dropdown

# Importa o motor de processamento (tenta importar para não quebrar se o arquivo não existir)
try:
    from processar_agenda import processar_pedidos_pdf_duas_paginas
except ImportError:
    processar_pedidos_pdf_duas_paginas = None

# --- Configuração de Logging Customizado para UI ---
class TextHandler(logging.Handler):
    """Redireciona logs para um widget de texto (Textbox) na interface."""
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record):
        msg = self.format(record)
        def append():
            self.text_widget.configure(state='normal')
            self.text_widget.insert('end', msg + '\n')
            self.text_widget.see('end')
            self.text_widget.configure(state='disabled')
        # Garante execução na main thread do Tkinter
        self.text_widget.after(0, append)

# Configuração Base
logger = config.setup_logging(__name__)
ctk.set_appearance_mode(config.UI_THEME_MODE)
ctk.set_default_color_theme(config.UI_COLOR_THEME)

class PedidoApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Gerador e Processador de Pedidos")
        self.geometry("1280x850") 

        # --- ATIVA SCROLL GLOBAL (Crucial para Linux) ---
#        enable_global_linux_scroll(self)

        config.ensure_directories()

        # --- Carregamento de Dados ---
        self.available_pdfs = self._load_pdf_list()
        self.available_fonts = self._load_font_list()
        self.templates_dict = self._load_templates()

        # --- Variáveis de Imagem (Preview) ---
        self.base_image_pil = None  
        self.preview_tk_image = None 
        self.zoom_factor = 1.0      

        # --- Variáveis de UI ---
        self.output_pdf_var = ctk.StringVar(value="")
        
        initial_pdf = self.available_pdfs[0] if self.available_pdfs else ""
        self.input_pdf_var = ctk.StringVar(value=initial_pdf)
        
        initial_tmpl = list(self.templates_dict.keys())[0] if self.templates_dict else ""
        self.template_id_var = ctk.StringVar(value=initial_tmpl)
        
        self.text_var = ctk.StringVar(value="")
        self.font_override_var = ctk.StringVar(value=config.DEFAULT_FONT_NAME)

        self.pedidos_em_lote = []

        # --- Setup ---
        self._setup_triggers()
        self._setup_ui()
        
        # Carrega preview inicial
        self._on_base_pdf_change() 

    def _setup_triggers(self):
        # Qualquer mudança nestas variáveis atualiza o preview ou carrega novo PDF
        self.input_pdf_var.trace_add("write", lambda *args: self._on_base_pdf_change())
        self.template_id_var.trace_add("write", lambda *args: self._update_preview())
        self.text_var.trace_add("write", lambda *args: self._update_preview())
        self.font_override_var.trace_add("write", lambda *args: self._update_preview())

    def _load_pdf_list(self):
        try:
            pdfs = sorted([f.name for f in config.DIR_PICTURES.iterdir() if f.suffix.lower() == '.pdf'])
            return pdfs if pdfs else ["(Nenhum PDF em /pictures)"]
        except Exception as e:
            return ["(Erro)"]

    def _load_font_list(self):
        try:
            fonts = ["(Padrão do Template)"]
            fonts += sorted([f.name for f in config.DIR_FONTS.iterdir() if f.suffix.lower() in ('.ttf', '.otf')])
            return fonts
        except Exception as e:
            return ["(Erro)"]

    def _load_templates(self):
        if not config.FILE_TEMPLATES_CONFIG.exists(): return {}
        try:
            with open(config.FILE_TEMPLATES_CONFIG, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if validate_data(data, 'templates'): return data
            return data if isinstance(data, dict) else {}
        except Exception: return {}

    def _setup_ui(self):
        # Layout Principal: 2 Colunas (Cima), Log e Botões (Baixo)
        self.grid_columnconfigure(0, weight=1) 
        self.grid_columnconfigure(1, weight=2) 
        self.grid_rowconfigure(0, weight=3) # Área Principal (Form + Preview)
        self.grid_rowconfigure(1, weight=1) # Log Area

        # === ÁREA SUPERIOR ===
        top_container = ctk.CTkFrame(self, fg_color="transparent")
        top_container.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=10, pady=5)
        top_container.grid_columnconfigure(0, weight=1)
        top_container.grid_columnconfigure(1, weight=2)
        top_container.grid_rowconfigure(0, weight=1)

        # -- Esquerda: Formulário --
        self.form_frame = ctk.CTkFrame(top_container)
        self.form_frame.grid(row=0, column=0, sticky="nsew", padx=(0,5))
        
        ctk.CTkLabel(self.form_frame, text="Novo Pedido", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10)
        
        self._create_input("1. Nome do PDF Final:", self.output_pdf_var, "ex: convite_joao.pdf")
        self._create_select("2. PDF Base:", self.input_pdf_var, self.available_pdfs)
        
        vals_tmpl = list(self.templates_dict.keys()) if self.templates_dict else ["(Sem templates)"]
        self._create_select("3. Template:", self.template_id_var, vals_tmpl)
        
        self._create_input("4. Texto:", self.text_var, "Digite o nome...")
        self._create_select("5. Fonte:", self.font_override_var, self.available_fonts)
        
        self.btn_add = ctk.CTkButton(self.form_frame, text="⬇ Adicionar à Fila", command=self._add_pedido_to_queue)
        self.btn_add.pack(pady=15, padx=10, fill="x")

        # -- Lista Rápida na Esquerda --
        ctk.CTkLabel(self.form_frame, text="Fila Atual:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10)
        self.scroll_list = ctk.CTkScrollableFrame(self.form_frame, height=150)
        self.scroll_list.pack(fill="both", expand=True, padx=10, pady=5)
        self._refresh_list_display()

        # -- Direita: Preview --
        self.right_panel = ctk.CTkFrame(top_container, fg_color="transparent")
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=(5,0))
        self.right_panel.grid_rowconfigure(1, weight=1)
        self.right_panel.grid_columnconfigure(0, weight=1)

        # Toolbar de Zoom
        self.zoom_bar = ctk.CTkFrame(self.right_panel, height=40)
        self.zoom_bar.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        
        ctk.CTkLabel(self.zoom_bar, text="Preview:").pack(side="left", padx=10)
        ctk.CTkButton(self.zoom_bar, text="-", width=30, command=self._zoom_out).pack(side="left", padx=2)
        self.zoom_label_percent = ctk.CTkLabel(self.zoom_bar, text="Fit", width=40)
        self.zoom_label_percent.pack(side="left", padx=2)
        ctk.CTkButton(self.zoom_bar, text="+", width=30, command=self._zoom_in).pack(side="left", padx=2)
        ctk.CTkButton(self.zoom_bar, text="Reset", width=60, command=self._zoom_reset, fg_color="gray").pack(side="left", padx=10)

        # Área da Imagem (com Scroll)
        self.preview_scroll_frame = ctk.CTkScrollableFrame(self.right_panel, fg_color="#2b2b2b")
        self.preview_scroll_frame.grid(row=1, column=0, sticky="nsew")
        
        self.preview_label = ctk.CTkLabel(self.preview_scroll_frame, text="")
        self.preview_label.pack(anchor="center", pady=10, padx=10)
        
        self.right_panel.bind("<Configure>", self._on_window_resize)

        # === ÁREA INFERIOR (Ações e Logs) ===
        self.bottom_frame = ctk.CTkFrame(self, height=200)
        self.bottom_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=10, sticky="nsew")
        self.bottom_frame.grid_columnconfigure(0, weight=1)
        self.bottom_frame.grid_columnconfigure(1, weight=1)
        self.bottom_frame.grid_rowconfigure(1, weight=1)

        # Botões de Ação
        btn_frame = ctk.CTkFrame(self.bottom_frame, fg_color="transparent")
        btn_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=5)
        
        self.btn_save = ctk.CTkButton(btn_frame, text="💾 SALVAR JSON", command=self._save_json_file, width=200)
        self.btn_save.pack(side="left", padx=20)

        self.btn_process = ctk.CTkButton(btn_frame, text="⚙ PROCESSAR LOTE AGORA", command=self._start_processing_thread, 
                                         fg_color="#D35B58", hover_color="#C72C41", width=200)
        self.btn_process.pack(side="right", padx=20)

        # Console de Logs
        ctk.CTkLabel(self.bottom_frame, text="Console de Execução:", font=ctk.CTkFont(size=12)).grid(row=1, column=0, sticky="w", padx=10)
        self.log_console = ctk.CTkTextbox(self.bottom_frame, height=100, font=("Consolas", 12))
        self.log_console.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=10, pady=(0,10))
        self.log_console.configure(state='disabled')

        # Conecta o logger ao widget de texto
        text_handler = TextHandler(self.log_console)
        text_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s', datefmt='%H:%M:%S'))
        logger.addHandler(text_handler)
        logging.getLogger().addHandler(text_handler) # Captura logs globais


    # --- HELPERS UI ---
    def _create_input(self, label, var, ph):
        ctk.CTkLabel(self.form_frame, text=label, anchor="w").pack(fill="x", padx=10, pady=(5,0))
        ctk.CTkEntry(self.form_frame, textvariable=var, placeholder_text=ph).pack(fill="x", padx=10, pady=2)

    def _create_select(self, label, var, values):
        ctk.CTkLabel(self.form_frame, text=label, anchor="w").pack(fill="x", padx=10, pady=(5,0))
        combo = ctk.CTkComboBox(self.form_frame, variable=var, values=[]) 
        combo.pack(fill="x", padx=10, pady=2)
        
        def on_select(val): var.set(val)
        # Usa o dropdown customizado do ui_utils.py
        attach_scrollable_dropdown(combo, values=values, command=on_select, height=250)

    # --- PROCESSAMENTO (THREAD) ---
    def _start_processing_thread(self):
        if not self.pedidos_em_lote:
            # Verifica se existe arquivo salvo para processar
            try:
                with open(config.FILE_PEDIDOS_DATA, 'r') as f:
                    data = json.load(f)
                    if data:
                        if messagebox.askyesno("Processar", "A fila da memória está vazia, mas existe um arquivo JSON salvo. Processá-lo?"):
                            pass 
                        else: return
                    else:
                        messagebox.showwarning("Vazio", "Nada para processar."); return
            except:
                messagebox.showwarning("Vazio", "Adicione pedidos à fila primeiro."); return

        self._save_json_file(silent=True)

        self.btn_process.configure(state="disabled", text="Processando...")
        self.log_console.configure(state='normal'); self.log_console.delete("1.0", "end"); self.log_console.configure(state='disabled')
        
        t = threading.Thread(target=self._run_processing)
        t.start()

    def _run_processing(self):
        try:
            if not processar_pedidos_pdf_duas_paginas:
                logger.error("ERRO: Módulo 'processar_agenda.py' não encontrado.")
                return

            logger.info(">>> INICIANDO MOTOR DE PROCESSAMENTO <<<")
            processar_pedidos_pdf_duas_paginas()
            logger.info(">>> PROCESSO FINALIZADO <<<")
            messagebox.showinfo("Concluído", "Processamento finalizado! Verifique a pasta 'output'.")
        except Exception as e:
            logger.error(f"Erro fatal na thread: {e}")
            messagebox.showerror("Erro Fatal", f"Ocorreu um erro: {e}")
        finally:
            self.btn_process.configure(state="normal", text="⚙ PROCESSAR LOTE AGORA")

    # --- SAVE JSON ---
    def _save_json_file(self, silent=False):
        if not self.pedidos_em_lote and not silent: return
        
        if validate_data(self.pedidos_em_lote, 'pedidos'):
            try:
                with open(config.FILE_PEDIDOS_DATA, 'w', encoding='utf-8') as f:
                    json.dump(self.pedidos_em_lote, f, indent=2, ensure_ascii=False)
                if not silent: 
                    messagebox.showinfo("Salvo", "Lista salva com sucesso!")
                    self.pedidos_em_lote = [] 
                    self._refresh_list_display()
            except Exception as e:
                logger.error(f"Erro save: {e}")
        else:
            if not silent: messagebox.showerror("Erro", "Dados inválidos.")

    # --- ZOOM & PREVIEW ---
    def _zoom_in(self): self.zoom_factor += 0.25; self._update_preview()
    def _zoom_out(self): 
        if self.zoom_factor > 0.25: self.zoom_factor -= 0.25; self._update_preview()
    def _zoom_reset(self): self.zoom_factor = 1.0; self._update_preview()
    def _on_window_resize(self, e): 
        if self.base_image_pil and abs(self.zoom_factor-1.0)<0.1: self._update_preview()

    def _on_base_pdf_change(self):
        p = self.input_pdf_var.get()
        if not p or p.startswith("("): return
        
        fp = config.DIR_PICTURES / p
        if not fp.exists(): return
        
        try:
            doc = fitz.open(fp)
            page = doc[0]
            
            # --- FIX CRÍTICO DE ESCALA (DPI) ---
            # O Editor usa 300 DPI. Devemos usar o mesmo aqui.
            # 300 DPI / 72 (padrão PDF) = ~4.1666
            scale_factor = 300 / 72
            pix = page.get_pixmap(matrix=fitz.Matrix(scale_factor, scale_factor))
            
            self.base_image_pil = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            doc.close()
            
            self.zoom_factor = 1.0 
            self._update_preview()
        except Exception as e: 
            logger.error(str(e))

    def _update_preview(self):
        if not self.base_image_pil: return
        
        self.zoom_label_percent.configure(text="Fit" if self.zoom_factor==1.0 else f"{int(self.zoom_factor*100)}%")
        
        # Copia imagem para desenhar
        img = self.base_image_pil.copy()
        draw = ImageDraw.Draw(img)
        
        tid = self.template_id_var.get()
        txt = self.text_var.get()
        fov = self.font_override_var.get()
        
        # Renderização do Template (Cálculo de Texto)
        if tid in self.templates_dict:
            t = self.templates_dict[tid]
            
            # Escolha da fonte
            ff = fov if (fov and fov!="(Padrão do Template)") else t.get("font_name", config.DEFAULT_FONT_NAME)
            fpath = config.DIR_FONTS / ff
            if not fpath.exists(): fpath = config.DIR_FONTS / config.DEFAULT_FONT_NAME
            
            try:
                font = ImageFont.truetype(str(fpath), t.get("font_size", 50))
                col = t.get("color", "#000000")
                align = t.get("align", "left")
                
                # Word Wrap
                lines = []
                words = txt.split()
                cline = ""
                for w in words:
                    test = f"{cline} {w}".strip()
                    bbox = draw.textbbox((0,0), test, font=font)
                    if (bbox[2]-bbox[0]) <= t.get("max_width_pixels", 500):
                        cline = test
                    else:
                        lines.append(cline)
                        cline = w
                lines.append(cline)
                
                # Desenho
                msk = font.getmask("hg")
                lh = msk.size[1] * 1.25
                cy = t.get("pos_y", 0)
                
                for l in lines:
                    bbox = draw.textbbox((0,0), l, font=font)
                    lw = bbox[2] - bbox[0]
                    dx = t.get("pos_x", 0)
                    
                    if align == "center": 
                        dx += (t.get("max_width_pixels", 500)/2) - (lw/2)
                    elif align == "right": 
                        dx += t.get("max_width_pixels", 500) - lw
                    
                    draw.text((dx, cy), l, font=font, fill=col)
                    cy += lh
            except Exception as e:
                logger.error(f"Erro render: {e}")

        # Redimensionamento para Tela (Viewport)
        vw = self.preview_scroll_frame.winfo_width()
        vh = self.preview_scroll_frame.winfo_height()
        if vw < 50: vw = 600
        if vh < 50: vh = 600
        
        iw, ih = img.size
        fit_scale = min(vw/iw, vh/ih)
        final_scale = fit_scale * self.zoom_factor
        
        nw, nh = max(1, int(iw * final_scale)), max(1, int(ih * final_scale))
        
        # Resize com qualidade
        img = img.resize((nw, nh), Image.Resampling.LANCZOS)
        
        # --- FIX: Usar CTkImage para evitar avisos e melhorar DPI ---
        self.preview_tk_image = ctk.CTkImage(light_image=img, dark_image=img, size=(nw, nh))
        self.preview_label.configure(image=self.preview_tk_image, text="")

    # --- ADICIONAR FILA (Com Fallback de Nome) ---
    def _add_pedido_to_queue(self):
        out_filename = self.output_pdf_var.get().strip()
        txt_content = self.text_var.get().strip()
        
        # Fallback: Se nome vazio, usa o texto
        if not out_filename:
            out_filename = txt_content

        if not out_filename:
            messagebox.showwarning("Aviso", "Obrigatório definir ao menos o Texto ou o Nome do arquivo.")
            return

        if not out_filename.lower().endswith(".pdf"):
            out_filename += ".pdf"
        
        base_pdf = self.input_pdf_var.get()
        tmpl_id = self.template_id_var.get()
        ov = self.font_override_var.get()
        font_final = None if ov == "(Padrão do Template)" else ov

        novo_pedido = {
            "output_pdf": out_filename,
            "input_pdf_base": base_pdf,
            "pagina_frente": {
                "template_imagem": tmpl_id,
                "texto": txt_content,
                "fonte": font_final
            }
        }

        self.pedidos_em_lote.append(novo_pedido)
        self._refresh_list_display()
        
        self.output_pdf_var.set("") 
        self.text_var.set("")
        try: self.focus() 
        except: pass

    def _refresh_list_display(self):
        for c in self.scroll_list.winfo_children(): c.destroy()
        
        if not self.pedidos_em_lote: 
            ctk.CTkLabel(self.scroll_list, text="Fila Vazia").pack()
            return
            
        for i, p in enumerate(self.pedidos_em_lote):
            f = ctk.CTkFrame(self.scroll_list)
            f.pack(fill="x", pady=2)
            
            lbl_txt = f"#{i+1} | {p['output_pdf']} | {p['pagina_frente']['texto']}"
            ctk.CTkLabel(f, text=lbl_txt, anchor="w").pack(side="left", padx=10)
            
            ctk.CTkButton(f, text="X", width=30, fg_color="red", 
                          command=lambda x=i: self._rm(x)).pack(side="right", padx=5)
    
    def _rm(self, i): 
        self.pedidos_em_lote.pop(i)
        self._refresh_list_display()

if __name__ == "__main__":
    app = PedidoApp()
    app.mainloop()