import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RentGuard AI | 계약 전 위험을 먼저 읽다",
  description: "전세계약 서류 교차검증과 위험 행동 가이드",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
