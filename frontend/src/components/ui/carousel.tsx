// Hand-written following the shadcn Carousel pattern — not copied from the registry.
import * as React from 'react'
import useEmblaCarousel, { type UseEmblaCarouselType } from 'embla-carousel-react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

type CarouselApi = UseEmblaCarouselType[1]

interface CarouselContextValue {
  emblaRef: UseEmblaCarouselType[0]
  api: CarouselApi
  canScrollPrev: boolean
  canScrollNext: boolean
  current: number
  count: number
  scrollPrev: () => void
  scrollNext: () => void
}

const CarouselContext = React.createContext<CarouselContextValue | null>(null)

function useCarousel() {
  const ctx = React.useContext(CarouselContext)
  if (!ctx) throw new Error('useCarousel must be used within <Carousel>')
  return ctx
}

function Carousel({ className, children, ...props }: React.ComponentProps<'div'>) {
  const [emblaRef, api] = useEmblaCarousel()
  const [canScrollPrev, setCanScrollPrev] = React.useState(false)
  const [canScrollNext, setCanScrollNext] = React.useState(false)
  const [current, setCurrent] = React.useState(0)
  const [count, setCount] = React.useState(0)

  const onSelect = React.useCallback((api: CarouselApi) => {
    if (!api) return
    setCanScrollPrev(api.canScrollPrev())
    setCanScrollNext(api.canScrollNext())
    setCurrent(api.selectedScrollSnap())
    setCount(api.scrollSnapList().length)
  }, [])

  React.useEffect(() => {
    if (!api) return
    onSelect(api)
    api.on('select', onSelect)
    api.on('reInit', onSelect)
    return () => { api.off('select', onSelect); api.off('reInit', onSelect) }
  }, [api, onSelect])

  return (
    <CarouselContext.Provider value={{
      emblaRef, api,
      canScrollPrev, canScrollNext,
      current, count,
      scrollPrev: () => api?.scrollPrev(),
      scrollNext: () => api?.scrollNext(),
    }}>
      <div className={cn('relative', className)} {...props}>
        {children}
      </div>
    </CarouselContext.Provider>
  )
}

function CarouselContent({ className, ...props }: React.ComponentProps<'div'>) {
  const { emblaRef } = useCarousel()
  return (
    <div ref={emblaRef} className="overflow-hidden">
      <div className={cn('flex -ml-1', className)} {...props} />
    </div>
  )
}

function CarouselItem({ className, ...props }: React.ComponentProps<'div'>) {
  return <div className={cn('min-w-0 shrink-0 grow-0 basis-full pl-1', className)} {...props} />
}

function CarouselPrevious({ className, ...props }: React.ComponentProps<typeof Button>) {
  const { canScrollPrev, scrollPrev } = useCarousel()
  return (
    <Button variant="outline" size="icon-sm" onClick={scrollPrev} disabled={!canScrollPrev} className={cn(className)} {...props}>
      <ChevronLeft />
    </Button>
  )
}

function CarouselNext({ className, ...props }: React.ComponentProps<typeof Button>) {
  const { canScrollNext, scrollNext } = useCarousel()
  return (
    <Button variant="outline" size="icon-sm" onClick={scrollNext} disabled={!canScrollNext} className={cn(className)} {...props}>
      <ChevronRight />
    </Button>
  )
}

function CarouselCounter({ className, ...props }: React.ComponentProps<'span'>) {
  const { current, count } = useCarousel()
  if (count === 0) return null
  return (
    <span className={cn('text-sm text-muted-foreground', className)} {...props}>
      {current + 1} of {count}
    </span>
  )
}

export { Carousel, CarouselContent, CarouselItem, CarouselPrevious, CarouselNext, CarouselCounter }
