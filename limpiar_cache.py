#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import csv
import shutil
import ctypes


def configurar_consola():
    try:
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
    except Exception:
        pass
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


configurar_consola()

NOMBRES_CACHE = {
    "cache",
    "caches",
    "cache2",
    "gpucache",
    "code cache",
    "codecache",
    "shadercache",
    "cachestorage",
    "temp",
    "tmp",
    "__pycache__",
    ".cache",
    "thumbnails",
    "cached",
}

EXCLUIR = {
    "windows",
    "program files",
    "program files (x86)",
    "$recycle.bin",
    "system volume information",
    "recovery",
    "perflogs",
}


def es_carpeta_cache(nombre: str) -> bool:
    n = nombre.strip().lower()
    return n in NOMBRES_CACHE


def tamano_carpeta(ruta: str) -> int:
    total = 0
    for base, _dirs, ficheros in os.walk(ruta, onerror=lambda e: None):
        for f in ficheros:
            fp = os.path.join(base, f)
            try:
                if not os.path.islink(fp):
                    total += os.path.getsize(fp)
            except (OSError, PermissionError):
                pass
    return total


def formato_tamano(num_bytes: int) -> str:
    tam = float(num_bytes)
    for unidad in ("B", "KB", "MB", "GB", "TB"):
        if tam < 1024.0:
            return f"{tam:.2f} {unidad}"
        tam /= 1024.0
    return f"{tam:.2f} PB"


def escanear(raiz: str):
    encontrados = []
    print(f"Escaneando '{raiz}' ... (esto puede tardar unos minutos)\n")

    for base, dirs, _ficheros in os.walk(raiz, topdown=True, onerror=lambda e: None):
        dirs[:] = [d for d in dirs if d.lower() not in EXCLUIR]

        for d in list(dirs):
            if es_carpeta_cache(d):
                ruta = os.path.join(base, d)
                if d in dirs:
                    dirs.remove(d)
                try:
                    tam = tamano_carpeta(ruta)
                    if tam > 0:
                        encontrados.append((ruta, tam))
                        print(f"  [{formato_tamano(tam):>10}]  {ruta}")
                except (OSError, PermissionError):
                    pass

    return encontrados


def mostrar_lista(encontrados, limite=15):
    filas = sorted(encontrados, key=lambda x: x[1], reverse=True)

    print("\n" + "=" * 90)
    print(f"CACHE MAS GRANDES (top {min(limite, len(filas))} de {len(filas)})")
    print("=" * 90)
    print(f"{'TAMANO':>10}  {'NOMBRE':<16}  {'CARPETA (padre)'}")
    print("-" * 90)

    for ruta, tam in filas[:limite]:
        nombre = os.path.basename(ruta.rstrip(os.sep))
        carpeta = os.path.dirname(ruta)
        print(f"{formato_tamano(tam):>10}  {nombre:<16}  {carpeta}")

    if len(filas) > limite:
        print(f"... y {len(filas) - limite} mas (ver el informe completo)")
    print("-" * 90)
    return filas


def guardar_informe(encontrados, base="informe_cache"):
    filas = sorted(encontrados, key=lambda x: x[1], reverse=True)
    total = sum(t for _r, t in filas)
    txt_path = base + ".txt"
    csv_path = base + ".csv"

    try:
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("INFORME DE CACHE\n")
            f.write("=" * 90 + "\n")
            f.write(f"{'NOMBRE':<18} | {'TAMANO':>10} | RUTA COMPLETA (carpeta\\archivo)\n")
            f.write("-" * 90 + "\n")
            for ruta, tam in filas:
                nombre = os.path.basename(ruta.rstrip(os.sep))
                f.write(f"{nombre:<18} | {formato_tamano(tam):>10} | {ruta}\n")
            f.write("-" * 90 + "\n")
            f.write(f"TOTAL: {len(filas)} carpetas  -  {formato_tamano(total)}\n")
    except OSError as e:
        print(f"\nNo se pudo guardar el informe TXT: {e}")

    try:
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["#", "Nombre", "Tamano", "Tamano (bytes)", "Ruta completa"])
            for i, (ruta, tam) in enumerate(filas, start=1):
                nombre = os.path.basename(ruta.rstrip(os.sep))
                w.writerow([i, nombre, formato_tamano(tam), tam, ruta])
            w.writerow([])
            w.writerow(["TOTAL", len(filas), formato_tamano(total), total, ""])
    except OSError as e:
        print(f"\nNo se pudo guardar el informe CSV: {e}")

    return txt_path, csv_path


def eliminar(encontrados):
    liberado = 0
    fallos = 0
    for ruta, tam in encontrados:
        try:
            shutil.rmtree(ruta, ignore_errors=False)
            liberado += tam
            print(f"  Eliminado: {ruta}")
        except (OSError, PermissionError):
            fallos += 1
            print(f"  NO se pudo eliminar (en uso o protegido): {ruta}")
    print(f"\nEspacio liberado: {formato_tamano(liberado)}")
    if fallos:
        print(f"{fallos} carpeta(s) no se pudieron eliminar "
              f"(prueba a cerrar los programas que las usan).")


def mover_a_papelera(encontrados):
    from ctypes import wintypes

    FO_DELETE = 3
    FOF_ALLOWUNDO = 0x0040
    FOF_NOCONFIRMATION = 0x0010
    FOF_SILENT = 0x0004
    FOF_NOERRORUI = 0x0400

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", ctypes.c_uint16),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    movido = 0
    fallos = 0
    for ruta, tam in encontrados:
        op = SHFILEOPSTRUCTW()
        op.wFunc = FO_DELETE
        op.pFrom = ruta + "\0\0"
        op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_NOERRORUI | FOF_SILENT
        res = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        if res == 0 and not op.fAnyOperationsAborted:
            movido += tam
            print(f"  A la papelera: {ruta}")
        else:
            fallos += 1
            print(f"  NO se pudo enviar (en uso o protegido): {ruta}")
    print(f"\nEnviado a la Papelera: {formato_tamano(movido)} "
          f"(puedes restaurarlo desde la Papelera de reciclaje)")
    if fallos:
        print(f"{fallos} carpeta(s) no se pudieron enviar "
              f"(prueba a cerrar los programas que las usan).")


def abrir_archivo(ruta):
    try:
        os.startfile(os.path.abspath(ruta))
    except Exception as e:
        print(f"No se pudo abrir el archivo: {e}")


def ruta_por_defecto() -> str:
    return os.environ.get("SystemDrive", "C:") + os.sep


LETRAS_3D = {
    "F": ["███████╗", "██╔════╝", "█████╗  ", "██╔══╝  ", "██║     ", "╚═╝     "],
    "U": ["██╗   ██╗", "██║   ██║", "██║   ██║", "██║   ██║", "╚██████╔╝", " ╚═════╝ "],
    "L": ["██╗     ", "██║     ", "██║     ", "██║     ", "███████╗", "╚══════╝"],
    "C": [" ██████╗", "██╔════╝", "██║     ", "██║     ", "╚██████╗", " ╚═════╝"],
    "E": ["███████╗", "██╔════╝", "█████╗  ", "██╔══╝  ", "███████╗", "╚══════╝"],
    "A": [" █████╗ ", "██╔══██╗", "███████║", "██╔══██║", "██║  ██║", "╚═╝  ╚═╝"],
    "N": ["███╗   ██╗", "████╗  ██║", "██╔██╗ ██║", "██║╚██╗██║", "██║ ╚████║", "╚═╝  ╚═══╝"],
    "H": ["██╗  ██╗", "██║  ██║", "███████║", "██╔══██║", "██║  ██║", "╚═╝  ╚═╝"],
    "I": ["██╗", "██║", "██║", "██║", "██║", "╚═╝"],
    ":": ["   ", "██╗", "╚═╝", "██╗", "╚═╝", "   "],
    " ": ["   ", "   ", "   ", "   ", "   ", "   "],
}


def render_3d(texto: str) -> str:
    filas = ["", "", "", "", "", ""]
    for ch in texto.upper():
        glifo = LETRAS_3D.get(ch, LETRAS_3D[" "])
        for i in range(6):
            filas[i] += glifo[i] + " "
    return "\n".join(filas)


def mostrar_banner():
    print()
    print(render_3d("FULL CLEAN"))
    print(render_3d("CACHE IN C:"))
    print("                                          by alvaroreta.com")
    print()


def elegir_carpeta_dialogo():
    try:
        import tkinter as tk
        from tkinter import filedialog
        raiz_tk = tk.Tk()
        raiz_tk.withdraw()
        raiz_tk.attributes("-topmost", True)
        carpeta = filedialog.askdirectory(
            title="Elige la carpeta donde buscar cache"
        )
        raiz_tk.destroy()
        return carpeta or None
    except Exception:
        ruta = input("Escribe la ruta de la carpeta: ").strip().strip('"')
        return ruta or None


def menu_principal():
    print("Elige una opcion:\n")
    print("  1. Borrar toda la cache del sistema  (C:\\)")
    print("  2. Seleccionar carpeta (explorador)")
    print("  3. Borrar cache de la carpeta actual")
    print("  0. Salir")

    opcion = input("\nOpcion: ").strip()

    if opcion == "1":
        return ruta_por_defecto()
    elif opcion == "2":
        carpeta = elegir_carpeta_dialogo()
        if not carpeta:
            print("\nNo se eligio ninguna carpeta.")
            return None
        return carpeta
    elif opcion == "3":
        return os.getcwd()
    elif opcion == "0":
        return None
    else:
        print("\nOpcion no valida.")
        return None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    forzar = "--si-eliminar" in sys.argv

    mostrar_banner()

    if args:
        raiz = args[0]
    else:
        raiz = menu_principal()
        if not raiz:
            print("\nSaliendo. No se hizo nada.")
            return

    if not os.path.exists(raiz):
        print(f"La ruta '{raiz}' no existe.")
        sys.exit(1)

    encontrados = escanear(raiz)

    if not encontrados:
        print("\nNo se encontraron carpetas de cache. ¡Todo limpio!")
        return

    mostrar_lista(encontrados, limite=15)
    txt_path, csv_path = guardar_informe(encontrados)

    total = sum(t for _r, t in encontrados)
    print("\n" + "=" * 60)
    print(f"Carpetas de cache encontradas: {len(encontrados)}")
    print(f"Espacio total ocupado:        {formato_tamano(total)}")
    print("=" * 60)
    print(f"Informe (Excel): {os.path.abspath(csv_path)}")
    print(f"Informe (texto): {os.path.abspath(txt_path)}")

    if forzar:
        print("\nEliminando todo (modo automatico)...\n")
        eliminar(encontrados)
        return

    while True:
        print("\n¿Que quieres hacer?\n")
        print("  1. Eliminar TODO definitivamente")
        print("  2. Enviar TODO a la Papelera de reciclaje (recuperable)")
        print("  3. Abrir el informe (Excel/txt) con toda la informacion")
        print("  0. Salir sin borrar nada")
        opcion = input("\nOpcion: ").strip()

        if opcion == "1":
            conf = input(
                f"\nSe eliminaran {len(encontrados)} carpetas "
                f"({formato_tamano(total)}) SIN pasar por la papelera.\n"
                f"Esto NO se puede deshacer. ¿Seguro? (s/N): "
            ).strip().lower()
            if conf == "s":
                print("\nEliminando...\n")
                eliminar(encontrados)
            else:
                print("Cancelado. No se borro nada.")
            return

        elif opcion == "2":
            print("\nEnviando todo a la Papelera...\n")
            mover_a_papelera(encontrados)
            return

        elif opcion == "3":
            print(f"\nAbriendo: {os.path.abspath(csv_path)}")
            abrir_archivo(csv_path)
            print("(Revisa el informe y vuelve aqui para elegir 1, 2 o 0)")

        elif opcion == "0":
            print("\nSaliendo. No se borro nada.")
            return

        else:
            print("Opcion no valida.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelado por el usuario.")
