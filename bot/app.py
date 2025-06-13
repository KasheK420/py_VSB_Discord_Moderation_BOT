import argparse


def main(args):
    # Rozhodně by se to nemělo startovat přes tenhle import, ale nemám nervy ted přepisovat ten startup :D
    # (future proofing) Až se to přepíše a udělá se z toho funkce/třída tak tam passnout případné spouštěcí argumenty
    import vsb_bot.startup


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    # parser.add_argument(...)
    main(parser.parse_args())
