---
name: edgeone-deploy-config
description: 帮用户填写腾讯云 EdgeOne Pages 创建项目页面的配置项——框架预设、根目录、输出目录、构建命令、安装命令、环境变量、生产分支。当用户说"这个项目部署 EdgeOne 怎么填""EdgeOne Pages 配置怎么选""帮我看看这几项怎么填""刚建好仓库要部署 EdgeOne"，或贴出 EdgeOne Pages 创建项目页面截图（含"框架预设""根目录""输出目录""构建命令""安装命令""环境变量"等字段）时使用。做法是读用户当前代码仓库的实际内容（package.json、配置文件、lockfile、.env.example）来判断答案，而不是凭经验猜。不适用于：EdgeOne 的 CDN 加速、DNS、证书等其他产品线配置；用户还没建好仓库、代码还在本地没推送的情况（那种先帮用户把仓库建起来,再回来用这个 skill）。
---

# EdgeOne Pages 部署配置助手

## 目标

用户在腾讯云 EdgeOne Pages 建项目,面对"框架预设 / 根目录 / 输出目录 / 构建命令 / 安装命令 / 环境变量"这几个字段,不知道该填什么。你的活是**读用户仓库里的实际代码**,把这几项的答案算出来,而不是凭印象背答案。

一句话定位:你不是 EdgeOne 的说明书,你是这个仓库的侦探。

## 核心原则:界面上的选项以用户看到的为准

EdgeOne Pages 的"框架预设"下拉列表具体有哪些选项、UI 措辞是什么,会随平台更新变化,你手上没有实时的权威清单。所以:

- **不要编造或断言某个框架预设选项一定存在**于下拉列表里。给建议时用"接近的是 XXX"这种措辞,并提醒用户"以实际下拉列表里的选项为准,没有完全匹配的就选'其他 / 无框架预设 / Other',手动填后面几项"。
- 如果用户能提供截图或贴出下拉列表的实际选项文字,直接照着选,不要自己另编一个。
- 你能稳拿准的是**根目录、输出目录、构建命令、安装命令、环境变量清单**——这些是从代码里读出来的事实,不是猜的。

## 工作流程

### 第一步:定位仓库

默认用户说的是当前工作目录里的项目。如果当前目录看不出是要部署的那个仓库(比如是个工作区套多个项目),问一句是哪个子目录。

monorepo(一个仓库多个子项目,比如 `apps/web`、`packages/site`)要先确认到底部署哪一个——这直接决定"根目录"怎么填,别猜。

### 第二步:判断根目录

- 单仓库单项目、`package.json` 就在仓库根:根目录填 `./`
- monorepo 且要部署的是某个子目录:根目录填那个相对路径,比如 `apps/web`
- 判断依据:找 `package.json`(或 `pubspec.yaml`、`Cargo.toml` 等对应技术栈的清单文件)实际所在位置,不要靠猜文件夹名字

### 第三步:识别技术栈,匹配框架预设

读 `package.json` 的 `dependencies` / `devDependencies`,以及仓库里的框架专属配置文件。判断优先级:配置文件 > 依赖包名 > 目录结构。

| 看到什么 | 对应技术栈 | 框架预设建议(以下拉列表实际选项为准) |
|---|---|---|
| `vite.config.{js,ts}` | Vite(不管上层是 React/Vue/Svelte) | Vite |
| `next.config.{js,mjs,ts}` | Next.js | Next.js |
| `nuxt.config.{js,ts}` | Nuxt | Nuxt.js |
| `angular.json` | Angular | Angular |
| `vue.config.js` 且无 vite | Vue CLI | Vue |
| `svelte.config.js` 且有 `@sveltejs/kit` | SvelteKit | SvelteKit |
| `astro.config.{js,mjs,ts}` | Astro | Astro |
| `gatsby-config.js` | Gatsby | Gatsby |
| `docusaurus.config.js` | Docusaurus | Docusaurus |
| `.vuepress/config.js` | VuePress | VuePress |
| `_config.yml` + `Gemfile` | Jekyll | Jekyll |
| `hexo` 在 `package.json` 依赖里 | Hexo | Hexo |
| `config.toml`/`config.yaml` + 无 `package.json` | Hugo | Hugo |
| `react-scripts` 在依赖里、无 vite 配置 | Create React App | Create React App |
| 纯 `.html`/`.css`/`.js`,没有构建步骤 | 静态站点 | 无框架预设 / 静态网站(Other) |

**重要提醒(SSR/服务端渲染框架):** Next.js、Nuxt 这类框架如果项目用了 SSR、API 路由、增量静态再生成(ISR)等服务端能力,EdgeOne Pages 是否原生支持、需不需要额外适配,这个你不确定就不要打包票——如实告诉用户"这个项目用了 SSR,建议部署前确认 EdgeOne Pages 对应预设是否支持,或者改成静态导出(`next export` / `nuxt generate`)"。不要替用户下结论说"肯定能跑"或"肯定不能跑"。

### 第四步:判断输出目录

优先级:框架自身约定 > `package.json` 里 `build` 脚本的显式参数 > 配置文件里的 `outDir`/`distDir`/`output` 字段。

| 技术栈 | 默认输出目录 | 去哪核实 |
|---|---|---|
| Vite | `dist` | `vite.config` 的 `build.outDir`,没写就是默认值 |
| Create React App | `build` | 固定,不可配 |
| Next.js(静态导出) | `out` | `next.config` 有没有 `output: 'export'`,导出目录默认 `out` |
| Nuxt 3 | `.output/public` | Nuxt 3 静态生成用 `nuxt generate`,产物在这 |
| VuePress | `docs/.vuepress/dist` | 看 `docs` 源目录实际路径,不一定是 `docs` |
| Docusaurus | `build` | 固定 |
| Hexo | `public` | 固定 |
| Hugo | `public` | 固定,除非 `config.toml` 里 `publishDir` 改了 |
| Angular | `dist/<project-name>` | 项目名从 `angular.json` 里读,不是固定的 `dist` |

**不要照抄这张表就完事**——一定去项目实际的配置文件里核实一遍,框架版本不同、用户自己改过配置,都会导致跟默认值不一样。

### 第五步:构建命令 / 安装命令

- **构建命令**:直接读 `package.json` 的 `scripts.build`。EdgeOne 表单里通常填 `npm run build`(或对应包管理器的等价写法),不要凭空编一个脚本名——如果 `package.json` 里没有 `build` 脚本,如实告诉用户"没找到 build 脚本,这项目可能不需要构建,或者脚本名不叫 build",别硬填。
- **安装命令**:看仓库根目录的 lockfile 类型判断包管理器,不要默认都是 npm:

  | 仓库里有 | 包管理器 | 安装命令 |
  |---|---|---|
  | `package-lock.json` | npm | `npm install`(CI 场景可建议 `npm ci`,更快更可复现) |
  | `yarn.lock` | yarn | `yarn install` |
  | `pnpm-lock.yaml` | pnpm | `pnpm install` |
  | `bun.lockb` / `bun.lock` | bun | `bun install` |

  多个 lockfile 同时存在是个坏信号(可能是不同人用了不同包管理器混进来),提醒用户但按最新修改时间或项目主要约定判断,不要装作没看见。

### 第六步:环境变量清单

**只列变量名,绝不读取或回显任何密钥的实际值。**

去处找变量名:
1. 仓库里的 `.env.example` / `.env.sample` / `.env.template`
2. `README.md` 里提到的"需要配置的环境变量"章节
3. 代码里直接 grep `process.env.XXX`(Node 生态)或框架特定写法(`import.meta.env.XXX` / `VITE_XXX`),交叉核对哪些是真正被用到的

列出来的时候标注清楚:
- 哪些是**构建时**需要(比如 Vite 的 `VITE_` 前缀、Next.js 的 `NEXT_PUBLIC_` 前缀变量,这些会被打进产物里,必须在 EdgeOne 的构建环境变量里配,不能只在运行时配)
- 哪些是**运行时**需要(后端 API key、数据库连接串这类,一般不带那些公开前缀)
- 值本身让用户自己去对应的密钥管理工具或本地 `.env`(不提交进仓库的那份)里复制,你不要替用户猜值,更不能把本地 `.env` 里读到的真实值写进回复或任何文件

### 第七步:生产分支 & 加速区域(简单带一句)

- **生产分支**:默认是仓库的默认分支(通常是 `main` 或 `master`),用 `git branch --show-current` 或看远程默认分支确认,不要不看就假设是 `main`。
- **加速区域**:这项是业务/成本决策(是否需要覆盖中国大陆),不是能从代码里读出来的事实。除非用户明确问,否则不要替用户拍板,可以提示"面向中国大陆用户就选含中国大陆的区域,纯海外用户可以不选"。

## 输出格式

给用户一张对照表,每项标"建议值 + 依据",而不是甩一堆孤零零的结论:

```
| 字段 | 建议填什么 | 依据 |
|---|---|---|
| 框架预设 | Vite | 检测到 vite.config.ts |
| 根目录 | ./ | package.json 在仓库根 |
| 输出目录 | dist | vite.config.ts 未自定义 outDir,用的是 Vite 默认值 |
| 构建命令 | npm run build | package.json scripts.build |
| 安装命令 | npm install | 仓库里是 package-lock.json |
| 环境变量 | VITE_API_BASE_URL(构建时,需要)| .env.example 里声明,代码里 import.meta.env.VITE_API_BASE_URL 引用 |
```

如果某一项判断不了(没有 build 脚本、框架预设没有对应下拉选项、根目录不确定是哪个子项目),在对应行如实写"判断不了,需要你确认:xxx",不要为了填满表格硬编一个答案。
