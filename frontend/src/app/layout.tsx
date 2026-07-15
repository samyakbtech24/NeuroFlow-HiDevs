import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import Sidebar from "@/components/Sidebar";
import Providers from "@/components/Providers";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "NeuroFlow Dashboard",
  description: "AI Observability and Evaluation Platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrainsMono.variable} h-full antialiased`}>
      <body className="min-h-full flex overflow-hidden bg-background text-content-primary font-sans">
        <Providers>
          {/* Fixed Left Navigation */}
          <Sidebar />
          
          {/* Main Workspace */}
          <main className="flex-1 flex flex-col h-full overflow-y-auto bg-background">
            <div className="flex-1 mx-auto w-full max-w-[1500px] p-8">
              {children}
            </div>
          </main>
        </Providers>
      </body>
    </html>
  );
}
