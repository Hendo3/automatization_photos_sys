import json
import logging
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont, ImageOps

# --- Módulos da Arquitetura ---
import config
from schemas_validator import validate_data
from ui_utils import attach_scrollable_dropdown

try:
    from processar_agenda import processar_pedidos_pdf_duas_paginas
except ImportError:
    processar_pedidos_pdf_duas_paginas = None


# --- Configuração de Logging ---
class TextHandler(logging.Handler):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record):
        msg = self.format(record)

        def append():
            self.text_widget.configure(state="normal")
            self.text_widget.insert("end", msg + "\n")
            self.text_widget.see("end")
            self.text_widget.configure(state="disabled")

        self.text_widget.after(0, append)


logger = config.setup_logging(__name__)
ctk.set_appearance_mode(config.UI_THEME_MODE)
ctk.set_default_color_theme(config.UI_COLOR_THEME)


class PedidoApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Gerador de Pedidos (Full Page Support)")
        self.geometry("1280x850")

        # --- ÍCONE ---
        try:
            icon_path = config.APP_ROOT / "app_icon.ico"
            png_path = config.APP_ROOT / "app_icon.png"
            if icon_path.exists():
                try:
                    self.iconbitmap(icon_path)
                except Exception:
                    pass
            if png_path.exists():
                self._icon_png_photo = tk.PhotoImage(file=str(png_path))
                self.iconphoto(False, self._icon_png_photo)
        except Exception:
            pass

        config.ensure_directories()

        # --- Dados ---
        self.available_pdfs = self._load_pdf_list()
        self.available_fonts = self._load_font_list()
        self.templates_dict = self._load_templates()

        # --- Variáveis (preview) ---
        self.base_image_pil = None
        self.overlay_image_pil = None
        self.preview_tk_image = None

        self.zoom_factor = 1.0
        self.zoom_mode = "fit"        # "fit" | "manual"
        self.manual_scale = None      # escala absoluta (float) quando em modo manual
        self.fit_scale_cache = None   # cache do "Fit" (recalcula só em resize/pdf change)

        # --- Variáveis de UI ---
        self.output_pdf_var = ctk.StringVar(value="")

        initial_pdf = self.available_pdfs[0] if self.available_pdfs else ""
        self.input_pdf_var = ctk.StringVar(value=initial_pdf)

        initial_tmpl = list(self.templates_dict.keys())[0] if self.templates_dict else ""
        self.template_id_var = ctk.StringVar(value=initial_tmpl)

        self.text_var = ctk.StringVar(value="")
        self.font_override_var = ctk.StringVar(value=config.DEFAULT_FONT_NAME)

        self.image_path_var = ctk.StringVar(value="")
        self.full_page_overlay_var = ctk.BooleanVar(value=False)

        # --- Fila ---
        self.pedidos_em_lote: list[dict] = []

        self._setup_ui()
        self._setup_triggers()
        self._on_base_pdf_change()

    # -------------------------
    # Triggers / Loaders
    # -------------------------
    def _setup_triggers(self):
        self.input_pdf_var.trace_add("write", lambda *args: self._on_base_pdf_change())
        self.template_id_var.trace_add("write", lambda *args: self._update_preview())
        self.text_var.trace_add("write", lambda *args: self._update_preview())
        self.font_override_var.trace_add("write", lambda *args: self._update_preview())
        self.image_path_var.trace_add("write", lambda *args: self._on_overlay_image_change())
        self.full_page_overlay_var.trace_add("write", lambda *args: self._update_preview())

    def _load_pdf_list(self):
        try:
            pdfs = sorted([f.name for f in config.DIR_PICTURES.iterdir() if f.suffix.lower() == ".pdf"])
            return pdfs if pdfs else ["(Nenhum PDF em /pictures)"]
        except Exception:
            return ["(Erro)"]

    def _load_font_list(self):
        try:
            fonts = ["(Padrão do Template)"]
            fonts += sorted([f.name for f in config.DIR_FONTS.iterdir() if f.suffix.lower() in (".ttf", ".otf")])
            return fonts
        except Exception:
            return ["(Erro)"]

    def _load_templates(self):
        if not config.FILE_TEMPLATES_CONFIG.exists():
            return {}
        try:
            with open(config.FILE_TEMPLATES_CONFIG, "r", encoding="utf-8") as f:
                data = json.load(f)
            if validate_data(data, "templates"):
                return data
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    # -------------------------
    # UI Helpers (FIX: existiam chamadas, mas não havia métodos)
    # -------------------------
    def _create_input(self, label: str, var: ctk.StringVar, placeholder: str = ""):
        ctk.CTkLabel(self.form_frame, text=label, anchor="w").pack(fill="x", padx=10, pady=(5, 0))
        entry = ctk.CTkEntry(self.form_frame, textvariable=var, placeholder_text=placeholder)
        entry.pack(fill="x", padx=10, pady=2)
        return entry

    def _create_select(self, label: str, var: ctk.StringVar, values: list[str]):
        ctk.CTkLabel(self.form_frame, text=label, anchor="w").pack(fill="x", padx=10, pady=(5, 0))

        def on_select(val: str):
            var.set(val)

        combo = ctk.CTkComboBox(self.form_frame, variable=var, values=[], state="readonly")
        combo.pack(fill="x", padx=10, pady=2)

        # garante exibir valor inicial (sem depender do dropdown nativo)
        try:
            combo.set(var.get())
        except Exception:
            pass

        attach_scrollable_dropdown(combo, values=values, command=on_select, height=250)
        return combo

    # -------------------------
    # UI Layout
    # -------------------------
    def _setup_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(0, weight=3)
        self.grid_rowconfigure(1, weight=1)

        # === TOPO ===
        top_container = ctk.CTkFrame(self, fg_color="transparent")
        top_container.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=10, pady=5)
        top_container.grid_columnconfigure(0, weight=1)
        top_container.grid_columnconfigure(1, weight=2)
        top_container.grid_rowconfigure(0, weight=1)

        # -- Form --
        self.form_frame = ctk.CTkFrame(top_container)
        self.form_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        ctk.CTkLabel(
            self.form_frame, text="Configuração do Pedido", font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=10)

        self._create_input("1. Nome do Arquivo Final:", self.output_pdf_var, "ex: convite_joao.pdf")
        self._create_select("2. PDF Base:", self.input_pdf_var, self.available_pdfs)

        vals_tmpl = list(self.templates_dict.keys()) if self.templates_dict else ["(Sem templates)"]
        self._create_select("3. Template:", self.template_id_var, vals_tmpl)

        self._create_input("4. Texto Principal:", self.text_var, "Digite o nome...")
        self._create_select("5. Fonte (Opcional):", self.font_override_var, self.available_fonts)

        # --- SELETOR DE IMAGEM ---
        ctk.CTkLabel(self.form_frame, text="6. Foto/Imagem (Opcional):", anchor="w").pack(
            fill="x", padx=10, pady=(5, 0)
        )
        img_row = ctk.CTkFrame(self.form_frame, fg_color="transparent")
        img_row.pack(fill="x", padx=10, pady=2)

        self.entry_img = ctk.CTkEntry(img_row, textvariable=self.image_path_var, placeholder_text="Selecione imagem...")
        self.entry_img.pack(side="left", fill="x", expand=True, padx=(0, 5))

        btn_search = ctk.CTkButton(img_row, text="📂", width=40, command=self._choose_image)
        btn_search.pack(side="right")

        # --- Opções da imagem ---
        opts_frame = ctk.CTkFrame(self.form_frame, fg_color="transparent")
        opts_frame.pack(fill="x", padx=10, pady=2)

        chk_full = ctk.CTkCheckBox(opts_frame, text="Cobrir 100% da Página", variable=self.full_page_overlay_var)
        chk_full.pack(side="left")

        btn_clear_img = ctk.CTkButton(
            opts_frame, text="Limpar", width=60, height=20, fg_color="gray", command=lambda: self.image_path_var.set("")
        )
        btn_clear_img.pack(side="right")

        self.btn_add = ctk.CTkButton(self.form_frame, text="⬇ Adicionar à Fila", command=self._add_pedido_to_queue)
        self.btn_add.pack(pady=15, padx=10, fill="x")

        # Lista Rápida
        ctk.CTkLabel(self.form_frame, text="Fila Atual:", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=10
        )
        self.scroll_list = ctk.CTkScrollableFrame(self.form_frame, height=150)
        self.scroll_list.pack(fill="both", expand=True, padx=10, pady=5)
        self._refresh_list_display()

        # -- Preview --
        self.right_panel = ctk.CTkFrame(top_container, fg_color="transparent")
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        self.right_panel.grid_rowconfigure(1, weight=1)
        self.right_panel.grid_columnconfigure(0, weight=1)

        self.zoom_bar = ctk.CTkFrame(self.right_panel, height=40)
        self.zoom_bar.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        ctk.CTkLabel(self.zoom_bar, text="Preview:").pack(side="left", padx=10)
        ctk.CTkButton(self.zoom_bar, text="-", width=30, command=self._zoom_out).pack(side="left", padx=2)
        self.zoom_label_percent = ctk.CTkLabel(self.zoom_bar, text="Fit", width=40)
        self.zoom_label_percent.pack(side="left", padx=2)
        ctk.CTkButton(self.zoom_bar, text="+", width=30, command=self._zoom_in).pack(side="left", padx=2)
        ctk.CTkButton(self.zoom_bar, text="Reset", width=60, command=self._zoom_reset, fg_color="gray").pack(
            side="left", padx=10
        )

        self.preview_scroll_frame = ctk.CTkScrollableFrame(self.right_panel, fg_color="#2b2b2b")
        self.preview_scroll_frame.grid(row=1, column=0, sticky="nsew")
        self.preview_label = ctk.CTkLabel(self.preview_scroll_frame, text="")
        self.preview_label.pack(anchor="center", pady=10, padx=10)
        self.right_panel.bind("<Configure>", self._on_window_resize)

        # === BAIXO ===
        self.bottom_frame = ctk.CTkFrame(self, height=200)
        self.bottom_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=10, sticky="nsew")
        self.bottom_frame.grid_columnconfigure(0, weight=1)
        self.bottom_frame.grid_columnconfigure(1, weight=1)
        self.bottom_frame.grid_rowconfigure(2, weight=1)

        btn_frame = ctk.CTkFrame(self.bottom_frame, fg_color="transparent")
        btn_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=5)

        self.btn_save = ctk.CTkButton(btn_frame, text="💾 SALVAR JSON", command=self._save_json_file, width=200)
        self.btn_save.pack(side="left", padx=20)

        self.btn_process = ctk.CTkButton(
            btn_frame,
            text="⚙ PROCESSAR LOTE AGORA",
            command=self._start_processing_thread,
            fg_color="#D35B58",
            hover_color="#C72C41",
            width=200,
        )
        self.btn_process.pack(side="right", padx=20)

        ctk.CTkLabel(self.bottom_frame, text="Console de Execução:", font=ctk.CTkFont(size=12)).grid(
            row=1, column=0, sticky="w", padx=10
        )
        self.log_console = ctk.CTkTextbox(self.bottom_frame, height=100, font=("Consolas", 12))
        self.log_console.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=10, pady=(0, 10))
        self.log_console.configure(state="disabled")

        text_handler = TextHandler(self.log_console)
        text_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s", datefmt="%H:%M:%S"))
        logger.addHandler(text_handler)
        logging.getLogger().addHandler(text_handler)

    # -------------------------
    # Fila (FIX: métodos faltando)
    # -------------------------
    def _add_pedido_to_queue(self):
        out_name = self.output_pdf_var.get().strip()
        if not out_name:
            out_name = self.text_var.get().strip().replace(" ", "_") + ".pdf"
            
        base_pdf = self.input_pdf_var.get()
        tmpl = self.template_id_var.get()

        pedido = {
            "output_pdf": out_name,
            "input_pdf_base": base_pdf,
            "template_id": tmpl,
            "text": self.text_var.get(),
            "font_override": self.font_override_var.get(),
            "image_path": self.image_path_var.get(),
            "full_page_overlay": bool(self.full_page_overlay_var.get()),
        }

        self.pedidos_em_lote.append(pedido)
        self._refresh_list_display()

    def _refresh_list_display(self):
        for child in self.scroll_list.winfo_children():
            child.destroy()

        if not self.pedidos_em_lote:
            ctk.CTkLabel(self.scroll_list, text="(fila vazia)", anchor="w").pack(fill="x", padx=6, pady=4)
            return

        for i, p in enumerate(self.pedidos_em_lote, start=1):
            txt = f"{i}. {p.get('output_pdf','')} | {p.get('input_pdf','')} | {p.get('template_id','')}"
            ctk.CTkLabel(self.scroll_list, text=txt, anchor="w").pack(fill="x", padx=6, pady=2)

    # -------------------------
    # Funções existentes
    # -------------------------
    def _choose_image(self):
        path = filedialog.askopenfilename(
            title="Selecione a Imagem",
            filetypes=[("Imagens", "*.jpg *.jpeg *.png *.webp"), ("Todos", "*.*")],
        )
        if path:
            self.image_path_var.set(path)

    def _on_overlay_image_change(self):
        path = self.image_path_var.get()
        if not path:
            self.overlay_image_pil = None
        else:
            try:
                self.overlay_image_pil = Image.open(path).convert("RGBA")
            except Exception as e:
                logger.error(f"Erro imagem: {e}")
                self.overlay_image_pil = None
        self._update_preview()

    def _on_base_pdf_change(self):
        p = self.input_pdf_var.get()
        if not p or p.startswith("("):
            return
        fp = config.DIR_PICTURES / p
        if not fp.exists():
            return
        try:
            doc = fitz.open(fp)
            scale_factor = 300 / 72
            page = doc.load_page(0)
            pix = page.get_pixmap(matrix=fitz.Matrix(scale_factor, scale_factor))
            self.base_image_pil = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            doc.close()

            self.zoom_factor = 1.0
            self.zoom_mode = "fit"
            self.manual_scale = None
            self.fit_scale_cache = None
            self._update_preview()
        except Exception as e:
            logger.error(str(e))

    def _get_fit_scale(self, img_w: int, img_h: int) -> float:
        vw = self.preview_scroll_frame.winfo_width()
        vh = self.preview_scroll_frame.winfo_height()
        if vw < 50:
            vw = 600
        if vh < 50:
            vh = 600
        return min(vw / img_w, vh / img_h)

    def _update_preview(self):
        # Evita callback durante construção da UI
        if not hasattr(self, "zoom_label_percent") or not hasattr(self, "preview_scroll_frame"):
            return
        if not self.base_image_pil:
            return

        # Preserva posição do scroll (evita “pulo” ao re-renderizar a imagem)
        canvas = getattr(self.preview_scroll_frame, "_parent_canvas", None)
        prev_x = prev_y = None
        try:
            if canvas is not None:
                prev_x = canvas.xview()[0]
                prev_y = canvas.yview()[0]
        except Exception:
            prev_x = prev_y = None

        img = self.base_image_pil.copy()
        draw = ImageDraw.Draw(img)
        page_w, page_h = img.size

        # === IMAGEM ===
        if self.overlay_image_pil:
            try:
                foto = self.overlay_image_pil.copy()
                is_full_page = self.full_page_overlay_var.get()

                if is_full_page:
                    foto = foto.resize((page_w, page_h), Image.Resampling.LANCZOS)
                    if foto.mode == "RGBA":
                        img.paste(foto, (0, 0), foto)
                    else:
                        img.paste(foto, (0, 0))
                else:
                    tid = self.template_id_var.get()
                    t = self.templates_dict.get(tid, {})
                    px = t.get("photo_x") or t.get("img_x") or t.get("image_x")
                    py = t.get("photo_y") or t.get("img_y") or t.get("image_y")
                    pw = t.get("photo_w") or t.get("img_w") or t.get("image_w")
                    ph = t.get("photo_h") or t.get("img_h") or t.get("image_h")

                    if px is not None and py is not None:
                        if pw and ph:
                            foto = ImageOps.fit(foto, (int(pw), int(ph)), centering=(0.5, 0.5))
                        dest_x, dest_y = int(px), int(py)
                    else:
                        target_w = int(page_w * 0.5)
                        ratio = target_w / float(foto.width)
                        target_h = int(foto.height * ratio)
                        foto = foto.resize((target_w, target_h), Image.Resampling.LANCZOS)
                        dest_x = (page_w - target_w) // 2
                        dest_y = (page_h - target_h) // 2

                    if foto.mode == "RGBA":
                        img.paste(foto, (dest_x, dest_y), foto)
                    else:
                        img.paste(foto, (dest_x, dest_y))
            except Exception as e:
                logger.error(f"Erro preview imagem: {e}")

        # === TEXTO ===
        tid = self.template_id_var.get()
        txt = self.text_var.get()
        fov = self.font_override_var.get()

        if tid in self.templates_dict:
            t = self.templates_dict[tid]
            ff = fov if (fov and fov != "(Padrão do Template)") else t.get("font_name", config.DEFAULT_FONT_NAME)
            fpath = config.DIR_FONTS / ff
            if not fpath.exists():
                fpath = config.DIR_FONTS / config.DEFAULT_FONT_NAME

            try:
                font = ImageFont.truetype(str(fpath), t.get("font_size", 50))
                col = t.get("color", "#000000")
                align = t.get("align", "left")

                lines = []
                words = txt.split()
                cline = ""
                for w in words:
                    test = f"{cline} {w}".strip()
                    bbox = draw.textbbox((0, 0), test, font=font)
                    if (bbox[2] - bbox[0]) <= t.get("max_width_pixels", 500):
                        cline = test
                    else:
                        if cline:
                            lines.append(cline)
                        cline = w
                if cline:
                    lines.append(cline)

                msk = font.getmask("hg")
                lh = msk.size[1] * 1.25
                cy = t.get("pos_y", 0)

                for l in lines:
                    bbox = draw.textbbox((0, 0), l, font=font)
                    lw = bbox[2] - bbox[0]
                    dx = t.get("pos_x", 0)
                    if align == "center":
                        dx += (t.get("max_width_pixels", 500) / 2) - (lw / 2)
                    elif align == "right":
                        dx += t.get("max_width_pixels", 500) - lw
                    draw.text((dx, cy), l, font=font, fill=col)
                    cy += lh
            except Exception:
                pass

        # === RESIZE FINAL (zoom estável) ===
        iw, ih = img.size

        # "Fit" agora é cacheado para não oscilar em cada update de texto/template
        if self.fit_scale_cache is None:
            try:
                self.fit_scale_cache = float(self._get_fit_scale(iw, ih))
            except Exception:
                self.fit_scale_cache = 1.0
        fit_scale_ref = self.fit_scale_cache if (self.fit_scale_cache and self.fit_scale_cache > 0) else 1.0

        if self.zoom_mode == "manual" and self.manual_scale:
            final_scale = float(self.manual_scale)
            zoom_pct = int((final_scale / fit_scale_ref) * 100)
            zoom_label = f"{zoom_pct}%"
        else:
            final_scale = float(fit_scale_ref)
            zoom_label = "Fit"

        self.zoom_label_percent.configure(text=zoom_label)

        # arredondamento consistente (reduz variação de 1px que pode disparar scrollbars)
        nw, nh = max(1, int(round(iw * final_scale))), max(1, int(round(ih * final_scale)))
        img = img.resize((nw, nh), Image.Resampling.LANCZOS)
        self.preview_tk_image = ctk.CTkImage(light_image=img, dark_image=img, size=(nw, nh))
        self.preview_label.configure(image=self.preview_tk_image, text="")

        # Restaura scroll depois do layout atualizar
        if canvas is not None and prev_x is not None and prev_y is not None:
            def _restore_scroll():
                try:
                    canvas.xview_moveto(prev_x)
                    canvas.yview_moveto(prev_y)
                except Exception:
                    pass
            try:
                self.after(0, _restore_scroll)
            except Exception:
                _restore_scroll()

    def _zoom_in(self):
        if not self.base_image_pil:
            return
        iw, ih = self.base_image_pil.size
        # usa cache de Fit como referência estável
        if self.fit_scale_cache is None:
            self.fit_scale_cache = float(self._get_fit_scale(iw, ih))
        fit_scale = self.fit_scale_cache if (self.fit_scale_cache and self.fit_scale_cache > 0) else 1.0
        if self.zoom_mode != "manual" or not self.manual_scale:
            self.zoom_mode = "manual"
            self.manual_scale = fit_scale
        self.manual_scale *= 1.25
        self._update_preview()

    def _zoom_out(self):
        if not self.base_image_pil:
            return
        iw, ih = self.base_image_pil.size
        if self.fit_scale_cache is None:
            self.fit_scale_cache = float(self._get_fit_scale(iw, ih))
        fit_scale = self.fit_scale_cache if (self.fit_scale_cache and self.fit_scale_cache > 0) else 1.0
        if self.zoom_mode != "manual" or not self.manual_scale:
            self.zoom_mode = "manual"
            self.manual_scale = fit_scale
        self.manual_scale /= 1.25
        self._update_preview()

    def _zoom_reset(self):
        self.zoom_mode = "fit"
        self.manual_scale = None
        self.zoom_factor = 1.0
        self.fit_scale_cache = None
        self._update_preview()

    def _on_window_resize(self, _e):
        # Só recalcula Fit quando estiver em modo Fit (e invalida o cache)
        if self.base_image_pil and self.zoom_mode == "fit":
            self.fit_scale_cache = None
            self._update_preview()

    def _start_processing_thread(self):
        if not self.pedidos_em_lote:
            try:
                with open(config.FILE_PEDIDOS_DATA, "r", encoding="utf-8") as f:
                    if json.load(f):
                        if not messagebox.askyesno("Processar", "Fila vazia, processar arquivo salvo?"):
                            return
                    else:
                        messagebox.showwarning("Vazio", "Nada para processar.")
                        return
            except Exception:
                messagebox.showwarning("Vazio", "Fila vazia.")
                return

        self._save_json_file(silent=True)
        self.btn_process.configure(state="disabled", text="Processando...")
        self.log_console.configure(state="normal")
        self.log_console.delete("1.0", "end")
        self.log_console.configure(state="disabled")
        threading.Thread(target=self._run_processing, daemon=True).start()

    def _run_processing(self):
        try:
            if not processar_pedidos_pdf_duas_paginas:
                logger.error("ERRO: Motor 'processar_agenda' não encontrado.")
                return
            logger.info(">>> INICIANDO <<<")
            processar_pedidos_pdf_duas_paginas()
            logger.info(">>> FIM <<<")
            messagebox.showinfo("Sucesso", "Processamento concluído.")
        except Exception as e:
            logger.error(f"Erro Fatal: {e}")
            messagebox.showerror("Erro", str(e))
        finally:
            self.btn_process.configure(state="normal", text="⚙ PROCESSAR LOTE AGORA")

    def _save_json_file(self, silent=False):
        if not self.pedidos_em_lote and not silent:
            return
        if validate_data(self.pedidos_em_lote, "pedidos"):
            try:
                with open(config.FILE_PEDIDOS_DATA, "w", encoding="utf-8") as f:
                    json.dump(self.pedidos_em_lote, f, indent=2, ensure_ascii=False)
                if not silent:
                    messagebox.showinfo("Salvo", "Lista salva!")
                    self.pedidos_em_lote = []
                    self._refresh_list_display()
            except Exception as e:
                logger.error(str(e))
        else:
            if not silent:
                messagebox.showerror("Erro", "Dados inválidos.")


if __name__ == "__main__":
    app = PedidoApp()
    app.mainloop()