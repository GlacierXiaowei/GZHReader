# GZHReader Desktop

桌面端使用 Tauri 2、Vue 3、TypeScript、Vite 和 Pinia。

```powershell
npm ci
npm run dev
npm run build
npm run desktop:dev
npm run desktop:build
```

`desktop:dev` 和 `desktop:build` 需要：

- `src-tauri/binaries/gzhreader-core-x86_64-pc-windows-msvc.exe`
- Rust stable
- Visual Studio Build Tools 2022（MSVC C++ 与 Windows SDK）

Sidecar 请从仓库根目录运行 `scripts/build_sidecar.ps1` 生成。
