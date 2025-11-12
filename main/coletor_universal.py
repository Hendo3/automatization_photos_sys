import shutil
import logging
from pathlib import Path

# --- Configuração ---
# 1. A pasta principal que contém sua estrutura (ex: 'mae')
PASTA_MAE = "mae" 

# 2. A pasta de destino para onde tudo será copiado
PASTA_SAIDA = "saida_final"

# 3. Extensões dos arquivos que queremos "coletar"
EXTENSOES_ALVO = ['.pdf', '.ttf', '.otf', '.woff', '.woff2']
# --- Fim da Configuração ---

# Configura o logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def processar_arquivos_universal():
    """
    Varre a PASTA_MAE, encontra todos os arquivos com as extensões alvo (PDFs, Fontes)
    e copia-os para a PASTA_SAIDA com o nome da pasta-pai.
    """
    
    pasta_mae_path = Path(PASTA_MAE).resolve()
    pasta_saida_path = Path(PASTA_SAIDA).resolve()
    
    pasta_saida_path.mkdir(exist_ok=True)
    logging.info(f"Pasta de saída '{pasta_saida_path.name}' pronta.")
    
    if not pasta_mae_path.exists():
        logging.critical(f"ERRO: A pasta mãe '{PASTA_MAE}' não foi encontrada.")
        return

    arquivos_encontrados = []
    
    # 1. Varredura (o "ls -r" para todas as extensões)
    logging.info(f"Varrendo '{PASTA_MAE}' em busca de {EXTENSOES_ALVO}...")
    for ext in EXTENSOES_ALVO:
        # rglob('*.ext') varre todas as subpastas
        arquivos_encontrados.extend(pasta_mae_path.rglob(f'*{ext}'))
    
    if not arquivos_encontrados:
        logging.warning(f"Nenhum arquivo com as extensões alvo foi encontrado em '{PASTA_MAE}'.")
        return

    logging.info(f"Encontrados {len(arquivos_encontrados)} arquivos. Iniciando cópia...")
    
    arquivos_copiados = 0
    conflitos = 0

    for file_path in arquivos_encontrados:
        
        # 2. Definir o novo nome (a "mesma lógica")
        # Pega o nome da pasta que contém o arquivo (ex: '1.1.1' ou '2.1')
        nome_da_pasta_pai = file_path.parent.name
        
        # Pega a extensão original (ex: '.pdf' ou '.ttf')
        extensao_original = file_path.suffix
        
        # O nome base é o nome da pasta
        novo_nome_base = nome_da_pasta_pai
        
        # Define o caminho de destino (ex: /saida/1.1.1.pdf ou /saida/2.1.ttf)
        novo_path_destino = pasta_saida_path / f"{novo_nome_base}{extensao_original}"
        
        # 3. Copiar o arquivo (o "cp")
        try:
            # Verifica se já existe um arquivo com esse nome (ex: um PDF e uma Fonte na mesma pasta)
            if novo_path_destino.exists():
                logging.warning(f"CONFLITO: O arquivo '{novo_path_destino.name}' já existe. "
                                f"O arquivo '{file_path.name}' (da pasta {nome_da_pasta_pai}) não será copiado.")
                conflitos += 1
            else:
                shutil.copy2(file_path, novo_path_destino)
                logging.info(f"Copiado: '{file_path.name}' (de {nome_da_pasta_pai}) -> '{novo_path_destino.name}'")
                arquivos_copiados += 1
        except Exception as e:
            logging.error(f"Falha ao copiar '{file_path.name}': {e}")
            
    logging.info("--- Processamento Concluído ---")
    logging.info(f"Arquivos copiados com sucesso: {arquivos_copiados}")
    logging.info(f"Conflitos (arquivos pulados): {conflitos}")

# --- Ponto de Entrada do Script ---
if __name__ == "__main__":
    
    # Configuração da estrutura de pastas de exemplo (APENAS PARA TESTE)
    def criar_estrutura_de_teste():
        logging.info("Criando estrutura de pastas de teste...")
        # Limpa pastas antigas se existirem
        if Path("mae").exists(): shutil.rmtree("mae")
        if Path("saida_final").exists(): shutil.rmtree("saida_final")
        
        # Grupo 1: PDF e Fonte na mesma pasta (vai gerar conflito)
        Path("mae/grupo1").mkdir(parents=True, exist_ok=True)
        (Path("mae/grupo1") / "documento.pdf").write_text("conteudo pdf 1")
        (Path("mae/grupo1") / "minha_fonte.ttf").write_text("conteudo fonte 1")
        
        # Grupo 2: PDF e Fonte em pastas diferentes
        Path("mae/grupo2/pdf_aqui").mkdir(parents=True, exist_ok=True)
        (Path("mae/grupo2/pdf_aqui") / "relatorio.pdf").write_text("conteudo pdf 2")
        Path("mae/grupo2/fonte_aqui").mkdir(parents=True, exist_ok=True)
        (Path("mae/grupo2/fonte_aqui") / "outra_fonte.otf").write_text("conteudo fonte 2")

        logging.info("Estrutura de teste criada.")
    
    # Descomente a linha abaixo para criar a estrutura de teste:
    # criar_estrutura_de_teste() 
    
    # Executa a função principal
    processar_arquivos_universal()
