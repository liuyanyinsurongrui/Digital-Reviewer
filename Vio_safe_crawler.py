import asyncio
import random
import re
from typing import List, Dict, Any
from urllib.parse import urljoin
from playwright.async_api import async_playwright

class TlsSafeCrawler:
    """
    深度扫描优化爬虫�?(Playwright 驱动) - V4 强化�?
    1. 支持背景图、响应式图片、视频封�?
    2. 深度过滤 SVG 和内联图�?
    3. 支持动态加载触�?(Auto-Scroll)
    4. 智能去重与高清溯�?
    """
    def __init__(self, headless=True, executable_path=None, jitter_range=(1, 3)):
        self.headless = headless
        self.executable_path = executable_path
        self.jitter_range = jitter_range
        self.playwright = None
        self.browser = None
        self.context = None

    async def init_browser(self):
        """初始化浏览器"""
        if not self.playwright:
            self.playwright = await async_playwright().start()
            
        # 增加活性检查，如果浏览器实例已断开则重�?
        if self.browser and not self.browser.is_connected():
            print("⚠️ 浏览器连接已断开，正在尝试重�?..")
            self.browser = None
            self.context = None

        if not self.browser:
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-web-security"
            ]
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                executable_path=self.executable_path,
                args=launch_args
            )
            self.context = await self.browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                ignore_https_errors=True
            )

    async def close_browser(self):
        """关闭驱动"""
        if self.context:
            await self.context.close()
            self.context = None
        if self.browser:
            await self.browser.close()
            self.browser = None
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None

    async def crawl(self, url: str) -> Dict[str, Any]:
        """核心解析逻辑"""
        result = {'text': '', 'images': [], 'error': None}

        try:
            if self.jitter_range:
                delay = random.uniform(*self.jitter_range)
                print(f"�?抗频率限制：随机延迟 {delay:.2f}s...")
                await asyncio.sleep(delay)

            await self.init_browser()
            page = await self.context.new_page()
            
            print(f"🌐 正在深度解析落地�? {url}")
            await page.goto(url, wait_until="load", timeout=20000)
            
            # --- 自动触发懒加�?---
            await page.evaluate('''async () => {
                const distance = 500;
                const steps = 4;
                for (let i = 0; i < steps; i++) {
                    window.scrollBy(0, distance);
                    await new Promise(resolve => setTimeout(resolve, 200));
                }
                window.scrollTo(0, 0);
            }''')
            
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except: pass

            # 1. 结构化文字提�?(深度清洗版：剔除代码块与冗余空行，已解决 Python 转义警告)
            result['text'] = await page.evaluate(r'''() => {
                const bodyClone = document.body.cloneNode(true);

                // A. 强制剔除所有纯代码、样式和非文本标�?
                const noiseTags = bodyClone.querySelectorAll('script, style, noscript, template, svg, iframe, symbol');
                noiseTags.forEach(el => el.remove());

                // B. 剔除页头、页脚等工具区域
                const utils = bodyClone.querySelectorAll('header, footer, nav, [class*="header"], [class*="footer"], [class*="nav"], [id*="header"], [id*="footer"], [id*="nav"]');
                utils.forEach(el => el.remove());

                // C. 提取关键元数�?
                const pageTitle = document.title || "";
                const metaDesc = document.querySelector('meta[name="description"]')?.content || "";
                const mainH1 = document.querySelector('h1')?.innerText || "";

                // D. 获取清洗后的正文并进行行级提�?(优化版：彻底去除每行缩进与多余空�?
                let rawText = bodyClone.innerText || "";
                
                // 处理步骤�?
                // 1. 按行分割
                // 2. 去掉每行前后的空�?(解决缩进问题)
                // 3. 过滤掉完全空的行 (解决大段空白问题)
                let cleanLines = rawText.split('\n')
                                        .map(line => line.trim())
                                        .filter(line => line.length > 0);
                
                // 4. 用单个换行符重新合并
                let cleanContent = cleanLines.join('\n');

                return `[PAGE TITLE]: ${pageTitle.trim()}\n` +
                       `[META DESCRIPTION]: ${metaDesc.trim()}\n` +
                       `[MAIN HEADING]: ${mainH1.trim()}\n\n` +
                       `[CLEAN BODY CONTENT]:\n${cleanContent}`;
            }''')
            
            # 2. 提取图片 (在浏览器端执行复杂逻辑，已解决 Python 转义警告)
            result['images'] = await page.evaluate(r'''() => {
                const MIN_SIZE = 50; 
                const imgSet = new Set();
                
                // 辅助：判断是否为支持的图片格�?(采用白名单，排除 SVG/GIF/AVIF 等不稳定格式)
                const isInvalid = (path) => {
                    if (!path) return true;
                    if (path.startsWith('data:image/svg+xml')) return true;
                    // 仅允许主流格式，避免大模型无法解�?
                    const p = path.toLowerCase().split('?')[0];
                    const supported = ['.jpg', '.jpeg', '.png', '.webp', '.bmp'];
                    return !supported.some(ext => p.endsWith(ext));
                };

                // 辅助：判断是否为弹窗、通知、页头、页脚等非产品区域图�?
                const isUtilityArea = (el) => {
                    let curr = el;
                    while (curr && curr !== document.body) {
                        const tag = curr.tagName;
                        const cls = (curr.className || "").toString().toLowerCase();
                        const id = (curr.id || "").toString().toLowerCase();
                        
                        // 1. 弹窗/通知/挂件过滤
                        if (cls.includes('popup') || cls.includes('notification') || cls.includes('widget') || 
                            cls.includes('toast') || cls.includes('sales-pop') || cls.includes('modal') ||
                            id.includes('popup') || id.includes('notification')) return true;
                        
                        // 2. 头部/导航过滤
                        if (tag === 'HEADER' || tag === 'NAV' || 
                            cls.includes('header') || cls.includes('navbar') || cls.includes('nav-') ||
                            id.includes('header') || id.includes('nav')) return true;
                            
                        // 3. 底部/订阅/版权过滤
                        if (tag === 'FOOTER' || 
                            cls.includes('footer') || cls.includes('copyright') || cls.includes('newsletter') || 
                            cls.includes('subscribe') || id.includes('footer') || id.includes('copyright')) return true;

                        curr = curr.parentElement;
                    }
                    
                    const style = window.getComputedStyle(el);
                    if (style.position === 'fixed' || style.position === 'sticky') return true;
                    return false;
                };

                const extract = (el) => {
                    // 仅处理有物理尺寸或可见的元素 (要求宽高均不得小�?51 像素，防�?50x1 这种畸形�?
                    const w = el.offsetWidth || el.naturalWidth || 0;
                    const h = el.offsetHeight || el.naturalHeight || 0;
                    if ((w <= 50 || h <= 50) && el.tagName !== 'VIDEO') return;
                    
                    // 排除非产品内容区�?(弹窗、头尾等)
                    if (isUtilityArea(el)) return;

                    // A. 处理 IMG 标签
                    if (el.tagName === 'IMG') {
                        const attrs = ['data-src', 'data-url', 'data-original', 'src', 'currentSrc'];
                        for (let a of attrs) {
                            let v = el.getAttribute(a);
                            if (v && v.startsWith('http') && !isInvalid(v)) {
                                imgSet.add(v);
                                break;
                            }
                        }
                        // 处理 srcset (提取第一个作为备�?
                        const srcset = el.getAttribute('srcset');
                        if (srcset) {
                            const first = srcset.split(',')[0].trim().split(' ')[0];
                            if (first.startsWith('http') && !isInvalid(first)) imgSet.add(first);
                        }
                    }
                    // B. 处理 VIDEO 封面
                    else if (el.tagName === 'VIDEO') {
                        const poster = el.getAttribute('poster');
                        if (poster && poster.startsWith('http') && !isInvalid(poster)) imgSet.add(poster);
                    }
                    // C. 处理背景�?(同样进行尺寸校验)
                    const bg = window.getComputedStyle(el).backgroundImage;
                    if (bg && bg !== 'none' && bg.includes('url')) {
                        const m = bg.match(/url\(["']?(.*?)["']?\)/);
                        if (m && m[1] && m[1].startsWith('http') && !isInvalid(m[1])) {
                             const bw = el.offsetWidth || 0;
                             const bh = el.offsetHeight || 0;
                             if (bw > 50 && bh > 50) {
                                 imgSet.add(m[1]);
                             }
                        }
                    }
                };

                document.querySelectorAll('*').forEach(extract);

                // --- 溯源与去�?---
                const getCore = (url) => {
                    let u = url.split('?')[0];
                    const m = u.match(/-(\d+)(?:x\d+)?\.(jpg|jpeg|png|webp|avif|gif)$/i);
                    return {
                        core: m ? u.replace("-" + m[1], "") : u,
                        size: m ? parseInt(m[1]) : 0
                    };
                };

                const map = new Map();
                Array.from(imgSet).forEach(u => {
                    const { core, size } = getCore(u);
                    const exist = map.get(core);
                    if (!exist || size > exist.size) map.set(core, { url: u, size });
                });
                
                return Array.from(map.values()).map(e => e.url);
            }''')

            await page.close()

        except Exception as e:
            result['error'] = str(e)
            print(f"�?详情页解析异�? {e}")
            
        return result
