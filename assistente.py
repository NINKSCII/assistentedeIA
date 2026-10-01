import speech_recognition as sr
import os
import subprocess
import ollama
from gtts import gTTS
import pygame
import json
import re
import time
import send2trash # Apaga mandando para a Lixeira (mais seguro)
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import unicodedata

# ==========================================
# CONFIGURAÇÕES
# ==========================================
NOME_IA = "aurora" 
MODELO_OLLAMA = "llama3.1" 

pygame.mixer.init()

# Mapeando pastas padrão do seu usuário ( hamud habibi )
PASTAS_BASE = {
    "desktop": os.path.join(os.path.expanduser("~"), "Desktop"),
    "área de trabalho": os.path.join(os.path.expanduser("~"), "Desktop"),
    "documentos": os.path.join(os.path.expanduser("~"), "Documents"),
    "downloads": os.path.join(os.path.expanduser("~"), "Downloads")
}

APPS = {
    "calculadora": "calc.exe",
    "bloco de notas": "notepad.exe",
    "chrome": "chrome.exe",
    "edge": "msedge.exe"
}

# ==========================================
# FUNÇÕES BÁSICAS (FALAR E OUVIR)
# ==========================================
def falar(texto):
    print(f"IA: {texto}")
    try:
        arquivo_audio = "resposta_temp.mp3"
        pygame.mixer.music.stop()
        pygame.mixer.music.unload()
        
        tts = gTTS(text=texto, lang='pt-br')
        tts.save(arquivo_audio)
        
        pygame.mixer.music.load(arquivo_audio)
        pygame.mixer.music.play()
        
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
            
        pygame.mixer.music.unload()
            
    except Exception as e:
        print(f"Erro ao falar: {e}")

def ouvir():
    reconhecedor = sr.Recognizer()
    with sr.Microphone() as source:
        reconhecedor.adjust_for_ambient_noise(source, duration=1)
        while True:
            try:
                audio = reconhecedor.listen(source, timeout=None, phrase_time_limit=6)
                texto = reconhecedor.recognize_google(audio, language="pt-BR").lower()
                return texto
            except sr.UnknownValueError:
                continue
            except sr.RequestError:
                continue

def pedir_confirmacao():
    falar("Você tem certeza? Diga sim ou não.")
    resp = ouvir()
    return "sim" in resp

# ==========================================
# FUNÇÕES DE AÇÃO DO SISTEMA
# ==========================================
def limpar_nome(txt):
    # 1. Coloca em minúsculo
    txt = txt.lower()
    # 2. Se a IA inventar extensões no final, arranca elas antes de procurar!
    for ext in ['.exe', '.lnk', '.txt', '.pdf', '.docx', '.in', '.bat', '.mp3']:
        txt = txt.replace(ext, '')
    # 3. Remove acentos
    txt = unicodedata.normalize('NFD', txt).encode('ascii', 'ignore').decode('utf-8')
    # 4. Remove TUDO que não for letra ou número (espaços, underlines, traços)
    txt = re.sub(r'[^a-z0-9]', '', txt)
    return txt

def encontrar_caminho_real(nome_alvo, pasta_base=None):
    # Se o usuário não falou a pasta, busca em todas as 3 pastas automaticamente!
    if pasta_base and pasta_base.lower() in PASTAS_BASE:
        pastas_para_buscar = [PASTAS_BASE[pasta_base.lower()]]
    else:
        # CORREÇÃO DO BUG AQUI: alterado de "documents" para "documentos"
        pastas_para_buscar = [PASTAS_BASE["desktop"], PASTAS_BASE["downloads"], PASTAS_BASE["documentos"]]
        
    nome_busca = limpar_nome(nome_alvo) # Limpa o nome que a IA mandou
    
    for pasta_caminho in pastas_para_buscar:
        if not os.path.exists(pasta_caminho):
            continue
            
        for item in os.listdir(pasta_caminho):
            item_limpo = limpar_nome(item) # Limpa o nome real do PC tirando o .lnk etc
            
            # Se o nome que a IA mandou estiver dentro do nome do arquivo do PC
            if nome_busca in item_limpo:
                if "studio" not in nome_busca and "studio" in item_limpo:
                    continue # Pula o studio se não tiver pedido
                return os.path.join(pasta_caminho, item)
                
    return None # Não achou em nenhuma pasta

def abrir_arquivo(nome_alvo, pasta_base=None):
    caminho_completo = encontrar_caminho_real(nome_alvo, pasta_base)
    if caminho_completo:
        try:
            os.startfile(caminho_completo)
            nome_real = os.path.basename(caminho_completo)
            if os.path.isdir(caminho_completo):
                falar(f"Abrindo a pasta {nome_real}.")
            else:
                falar(f"Abrindo o arquivo {nome_real}.")
        except Exception as e:
            falar("Não consegui abrir isto.")
    else:
        falar(f"Não encontrei nada parecido com {nome_alvo} no seu computador.")


def excluir_arquivo(nome_alvo, pasta_base=None):
    caminho_completo = encontrar_caminho_real(nome_alvo, pasta_base)
    
    if caminho_completo:
        nome_real = os.path.basename(caminho_completo)
        tipo = "pasta" if os.path.isdir(caminho_completo) else "arquivo"
        
        if pedir_confirmacao():
            try:
                send2trash.send2trash(caminho_completo)
                falar(f"{tipo.capitalize()} {nome_real} movido para a lixeira.")
            except Exception as e:
                falar("Erro ao tentar apagar.")
        else:
            falar("Exclusão cancelada.")
    else:
        falar(f"Não encontrei nada parecido com {nome_alvo} para excluir.")


def criar_pasta(nome_pasta, pasta_base=None):
    # Se a IA alucinar o texto do prompt ou se não tiver a pasta, usa o Desktop
    if not pasta_base or "ou" in str(pasta_base).lower() or pasta_base.lower() not in PASTAS_BASE:
        pasta_caminho = PASTAS_BASE["desktop"]
    else:
        pasta_caminho = PASTAS_BASE[pasta_base.lower()]
        
    caminho_completo = os.path.join(pasta_caminho, nome_pasta)
    try:
        os.makedirs(caminho_completo, exist_ok=True)
        falar(f"Pasta {nome_pasta} criada com sucesso.")
    except Exception as e:
        print("Erro criar_pasta:", e)
        falar("Não consegui criar a pasta.")

# ==========================================
# PROMPT E CÉREBRO (OLLAMA)
# ==========================================
SYSTEM_PROMPT = """Você é a Aurora. Sua ÚNICA função é devolver um JSON válido.
REGRAS CRÍTICAS:
1. O valor da chave "pasta" ou "local" DEVE ser APENAS UMA palavra: "desktop", "documentos" ou "downloads". É PROIBIDO escrever a frase "desktop ou documentos ou downloads".
2. O nome da ação deve ser EXATAMENTE um destes: "abrir_app", "abrir_arquivo", "abrir_pasta", "excluir_arquivo", "excluir_pasta", "criar_pasta", "conversar". NÃO invente "abrir_aplicativo".
3. Para conversar, use OBRIGATORIAMENTE {"acao": "conversar", "resposta": "texto"}.
4. Se o usuário pedir para criar uma pasta e não der o nome, use "Nova Pasta".
5. NUNCA invente extensões (.exe, .lnk). Copie apenas o nome falado.

Ações permitidas:
- {"acao": "abrir_app", "app": "nome_do_app"}
- {"acao": "abrir_arquivo", "arquivo": "nome", "pasta": "desktop"}
- {"acao": "abrir_pasta", "pasta_alvo": "nome", "local": "desktop"}
- {"acao": "excluir_arquivo", "arquivo": "nome", "pasta": "desktop"}
- {"acao": "excluir_pasta", "pasta_alvo": "nome", "local": "desktop"}
- {"acao": "criar_pasta", "pasta": "desktop", "nome_pasta": "nome da nova pasta"}
- {"acao": "conversar", "resposta": "texto"}
"""

def processar_comando(comando):
    try:
        # O parâmetro format='json' força o Ollama a responder apenas com JSON válido!
        response = ollama.chat(model=MODELO_OLLAMA, format='json', messages=[
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': comando}
        ])
        resposta_ia = response['message']['content'].strip()
        print("Resposta Bruta da IA:", resposta_ia)
        
        try:
            dados = json.loads(resposta_ia)
        except json.JSONDecodeError:
            match = re.search(r'\{.*?\}', resposta_ia, re.DOTALL)
            if match:
                dados = json.loads(match.group(0))
            else:
                falar("Não entendi o comando. Pode repetir?")
                return
        
        acao = dados.get("acao")
        
        # PLANO B: Se a IA alucinar nomes parecidos com abrir_app, corrigimos
        if acao in ["abrir_aplicativo", "abrir_programa", "abrir_app"]:
            acao = "abrir_app"
            
        # Se a IA mandar JSON conversar errado, corrigimos
        if not acao and "conversar" in dados:
            acao = "conversar"
            dados = {"acao": "conversar", "resposta": dados.get("conversar")}
            
        # CAÇADOR DE CHAVES: Pega o local não importa qual nome a IA usou
        local = dados.get("pasta") or dados.get("local") or "desktop"
        
        if acao == "abrir_app":
            abrir_programa(dados.get("app"))
        elif acao == "abrir_arquivo":
            abrir_arquivo(dados.get("arquivo"), local)
        elif acao == "abrir_pasta":
            alvo = dados.get("pasta_alvo") or dados.get("arquivo")
            abrir_arquivo(alvo, local)
        elif acao == "excluir_arquivo":
            excluir_arquivo(dados.get("arquivo"), local)
        elif acao == "excluir_pasta":
            alvo = dados.get("pasta_alvo") or dados.get("arquivo")
            excluir_arquivo(alvo, local)
        elif acao == "criar_pasta":
            # CAÇADOR DE CHAVES: Pega o nome não importa qual chave a IA usou
            nome_pasta = dados.get("nome_pasta") or dados.get("nome_da_nova_pasta") or dados.get("nome") or "Nova Pasta"
            criar_pasta(nome_pasta, local)
        elif acao == "conversar":
            falar(dados.get("resposta"))
        else:
            falar("Não reconheci essa ação.")
            
    except Exception as e:
        print("Erro ao processar:", e)
        falar("Tive um problema ao processar isso.")

def abrir_programa(nome_app):
    if nome_app in APPS:
        try:
            os.startfile(APPS[nome_app])
            falar(f"Abrindo {nome_app}.")
        except Exception as e:
            falar("Não consegui abrir este programa.")
    else:
        falar(f"Não encontrei o programa {nome_app} na minha lista.")

# ==========================================
# LOOP PRINCIPAL
# ==========================================
def main():
    falar("Sistema iniciado com controle total. Diga aurora para me chamar.")
    while True:
        print("Ouvindo... (Diga 'aurora' para ativar)")
        texto = ouvir()
        if NOME_IA in texto:
            falar("Pois não?")
            print("Ouvindo comando...")
            comando = ouvir()
            if comando:
                print(f"Comando recebido: {comando}")
                processar_comando(comando)

if __name__ == "__main__":
    main()