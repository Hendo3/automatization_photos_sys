from PIL import Image, ImageDraw, ImageFont


def create_app_icon():
    # Tamanho base (Alta resolução)
    size = (256, 256)
    
    # Cria imagem transparente
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Cores
    paper_color = "#F5F5F5"
    fold_color = "#E0E0E0"
    outline_color = "#2B2B2B"
    accent_color = "#D35B58" # Vermelho tom suave
    
    # 1. Desenha o Papel (Documento) com canto dobrado
    # Polígono base: (x, y)
    coords = [
        (40, 20),   # Top Left
        (160, 20),  # Top Fold Start
        (216, 76),  # Fold End Right
        (216, 236), # Bottom Right
        (40, 236)   # Bottom Left
    ]
    draw.polygon(coords, fill=paper_color, outline=outline_color)
    
    # Borda grossa manual (já que polygon outline as vezes é fino)
    draw.line(coords + [coords[0]], fill=outline_color, width=5)

    # 2. Desenha a dobra (Orelha)
    fold_coords = [
        (160, 20),
        (160, 76),
        (216, 76)
    ]
    draw.polygon(fold_coords, fill=fold_color, outline=outline_color)
    draw.line(fold_coords + [fold_coords[0]], fill=outline_color, width=4)

    # 3. Decoração "PDF" (Faixa vermelha e linhas)
    # Faixa Vermelha
    draw.rectangle([70, 100, 186, 130], fill=accent_color)
    
    # Linhas de "texto" simulado
    draw.rectangle([70, 150, 186, 160], fill="#AAAAAA")
    draw.rectangle([70, 175, 186, 185], fill="#AAAAAA")
    draw.rectangle([70, 200, 140, 210], fill="#AAAAAA")

    # Texto "PDF" (Desenhado manualmente pra não depender de fonte externa)
    # P
    draw.line([(85, 105), (85, 125)], fill="white", width=4)
    draw.rectangle([85, 105, 95, 115], outline="white", width=4)
    # D
    draw.line([(105, 105), (105, 125)], fill="white", width=4)
    draw.line([(105, 105), (115, 115), (105, 125)], fill="white", width=4) # Curva tosca
    # F
    draw.line([(130, 105), (130, 125)], fill="white", width=4)
    draw.line([(130, 105), (145, 105)], fill="white", width=4)
    draw.line([(130, 115), (140, 115)], fill="white", width=4)

    # --- SALVAR ARQUIVOS ---
    
    # Salva .ICO (Para o Windows/PyInstaller)
    # Inclui vários tamanhos dentro do arquivo
    img.save("app_icon.ico", format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print("Gerado: app_icon.ico")

    # Salva .PNG (Para o Linux/UI)
    img.save("app_icon.png", format="PNG")
    print("Gerado: app_icon.png")

if __name__ == "__main__":
    create_app_icon()