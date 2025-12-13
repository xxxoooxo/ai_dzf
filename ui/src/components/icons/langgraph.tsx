/**
 * 版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。
 * 
 * 本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
 * 不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。
 * 
 * 授权商业应用请联系微信：huice666
 */
// NOTE  MC8yOmFIVnBZMlhuZzV2bmtJWTZNVEJrYXc9PTo1MDYyNmE0ZA==

export function LangGraphLogoSVG({
  className,
  width,
  height,
}: {
  width?: number;
  height?: number;
  className?: string;
}) {
  return (
    <svg
      width={width}
      height={height}
      viewBox="0 0 120 60"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      {/* 定义渐变 */}
      <defs>
        <linearGradient id="bgGradient" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" style={{ stopColor: "#1e3a8a", stopOpacity: 1 }} />
          <stop offset="100%" style={{ stopColor: "#3b82f6", stopOpacity: 1 }} />
        </linearGradient>
        <linearGradient id="accentGradient" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" style={{ stopColor: "#60a5fa", stopOpacity: 1 }} />
          <stop offset="100%" style={{ stopColor: "#3b82f6", stopOpacity: 1 }} />
        </linearGradient>
      </defs>

      {/* 主背景 */}
      <rect
        x="2"
        y="2"
        width="116"
        height="56"
        rx="28"
        fill="url(#bgGradient)"
        stroke="#1e40af"
        strokeWidth="1"
        opacity="0.95"
      />

      {/* 内层装饰边框 */}
      <rect
        x="6"
        y="6"
        width="108"
        height="48"
        rx="24"
        fill="none"
        stroke="#60a5fa"
        strokeWidth="0.5"
        opacity="0.3"
      />

      {/* 左侧装饰元素 */}
      <circle cx="22" cy="30" r="2.5" fill="#60a5fa" opacity="0.9" />
      <circle cx="22" cy="30" r="1" fill="#ffffff" opacity="0.8" />

      {/* 右侧装饰元素 */}
      <circle cx="98" cy="30" r="2.5" fill="#60a5fa" opacity="0.9" />
      <circle cx="98" cy="30" r="1" fill="#ffffff" opacity="0.8" />

      {/* "但" 字 */}
      <text
        x="38"
        y="39"
        fontFamily="'Microsoft YaHei', 'PingFang SC', sans-serif"
        fontSize="22"
        fontWeight="600"
        fill="#ffffff"
        textAnchor="middle"
        opacity="0.95"
      >
        但
      </text>

      {/* "问" 字 */}
      <text
        x="82"
        y="39"
        fontFamily="'Microsoft YaHei', 'PingFang SC', sans-serif"
        fontSize="22"
        fontWeight="600"
        fill="#ffffff"
        textAnchor="middle"
        opacity="0.95"
      >
        问
      </text>

      {/* 中间分隔线 - 使用渐变 */}
      <line
        x1="60"
        y1="16"
        x2="60"
        y2="44"
        stroke="url(#accentGradient)"
        strokeWidth="1.5"
        opacity="0.7"
      />

      {/* 顶部装饰线 */}
      <line
        x1="30"
        y1="12"
        x2="90"
        y2="12"
        stroke="#60a5fa"
        strokeWidth="0.8"
        opacity="0.4"
      />

      {/* 底部装饰线 */}
      <line
        x1="30"
        y1="48"
        x2="90"
        y2="48"
        stroke="#60a5fa"
        strokeWidth="0.8"
        opacity="0.4"
      />
    </svg>
  );
}
// eslint-disable  MS8yOmFIVnBZMlhuZzV2bmtJWTZNVEJrYXc9PTo1MDYyNmE0ZA==
