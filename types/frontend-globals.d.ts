declare const CryptoJS: any;
declare function io(...args: any[]): any;

declare var currentUser: any;
declare var currentRoom: any;
declare var currentRoomKey: string | null;
declare var currentRoomKeys: Record<string, string> | null;
declare var rooms: any[];
declare function escapeRegExp(value: string): string;

interface Window {
  [key: string]: any;
  DEBUG?: boolean;
}

interface EventTarget {
  [key: string]: any;
}

interface Element {
  [key: string]: any;
}

interface HTMLElement {
  [key: string]: any;
}

interface IdleDeadline {
  readonly didTimeout: boolean;
  timeRemaining(): DOMHighResTimeStamp;
}

interface IdleRequestOptions {
  timeout?: number;
}

declare function requestIdleCallback(
  callback: (deadline: IdleDeadline) => void,
  options?: IdleRequestOptions
): number;
