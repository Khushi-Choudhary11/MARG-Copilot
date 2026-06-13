export function trainIcon(trainType: string | null | undefined): string {
  switch (trainType) {
    case "Rajdhani":
    case "Vande Bharat":
      return "🚄";
    case "Shatabdi":
    case "Duronto":
      return "🚅";
    case "Garib Rath":
    case "AC Express":
    case "Superfast Express":
      return "🚆";
    case "Mail/Express":
      return "🚂";
    case "Passenger":
    case "EMU/DEMU":
      return "🚃";
    case "Goods":
      return "🚛";
    default:
      return "🚆";
  }
}
