import { useEffect, useState } from "react";

/** Theo dõi một media query (cập nhật khi xoay màn hình / đổi cỡ cửa sổ). */
export function useMedia(query: string): boolean {
  const get = () => (typeof window !== "undefined" && window.matchMedia ? window.matchMedia(query).matches : false);
  const [match, setMatch] = useState(get);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const on = () => setMatch(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [query]);
  return match;
}

export type Device = "phone" | "tablet" | "desktop";

/**
 * Thiết kế thích ứng (adaptive): ngoài CSS responsive, một số thành phần đổi HÀNH VI theo loại thiết bị —
 * vd. điện thoại mặc định xem 1 camera, dùng thanh điều hướng dưới, rút gọn số liệu.
 *   phone < 768px · tablet 768–1023px · desktop ≥ 1024px  (khớp breakpoint md / lg của Tailwind)
 */
export function useDevice(): Device {
  const md = useMedia("(min-width: 768px)");
  const lg = useMedia("(min-width: 1024px)");
  return lg ? "desktop" : md ? "tablet" : "phone";
}

/** Thiết bị cảm ứng (ưu tiên vùng chạm lớn, không dựa vào hover). */
export function useCoarsePointer(): boolean {
  return useMedia("(pointer: coarse)");
}
