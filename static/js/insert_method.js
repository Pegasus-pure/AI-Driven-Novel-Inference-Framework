const fs = require('fs');
const path = require('path');

const filePath = path.join(__dirname, 'pipeline-status.js');
let content = fs.readFileSync(filePath, 'utf8');

const newMethod = `
  /**
   * 恢复生成中状态（页面重连后调用）
   * @param {string} currentAgent - 后端当前正在执行的 agent 名称
   */
  restoreGenerating(currentAgent) {
    if (!currentAgent) return;

    const idx = this._stages.findIndex(s => s.agent === currentAgent);
    if (idx === -1) return;

    this._activeIndex = idx;
    this._visible = true;

    // 显示状态条
    if (this._bar) {
      this._bar.classList.add('pipeline-bar--active');
    }

    // 更新 UI
    this._updateUI();
  }
`;

// 在 hide() 方法结束后的空白处插入（在 "  }\n\n  // ── 显示模式切换" 之前）
const searchStr = '    // 清除顶部标签\n    if (this._label) {\n      this._label.textContent = \'\';\n    }\n  }\n\n  // ── 显示模式切换';
const replaceStr = '    // 清除顶部标签\n    if (this._label) {\n      this._label.textContent = \'\';\n    }\n  }\n' + newMethod + '\n  // ── 显示模式切换';

if (content.includes(searchStr)) {
  content = content.replace(searchStr, replaceStr);
  fs.writeFileSync(filePath, content, 'utf8');
  console.log('✅ restoreGenerating() 方法已插入');
} else {
  console.log('❌ 未找到插入位置');
  // 调试：输出前500字符
  const idx = content.indexOf('清除顶部标签');
  console.log('上下文:', content.substring(idx - 50, idx + 200));
}
